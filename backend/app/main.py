import logging
from contextlib import asynccontextmanager
from urllib.parse import quote
from typing import Literal

from fastapi import FastAPI, File, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException

from .config import Settings
from .documents import chunk_pages, extract_pdf, validate_upload
from .embeddings import LocalEmbeddings, retrieve
from .errors import AppError
from .gemini_service import GeminiAnswerer, insufficient
from .identity import IdentityRegistry
from .security import RequestGuard
from .store import Store
from .workspaces import WorkspaceStores

logger = logging.getLogger("clarityops")


class Prompt(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prompt: str = Field(min_length=2, max_length=1500)

    @field_validator("prompt")
    @classmethod
    def clean(cls, value):
        value = value.strip()
        if len(value) < 2:
            raise ValueError("Enter a question")
        return value


class NewMember(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    name: str = Field(min_length=1, max_length=80)
    role: Literal["owner", "employee"] = "employee"
    expires_in_days: int = Field(default=30, ge=1, le=30)


def create_app(settings=None, embeddings=None, answerer=None):
    settings = settings or Settings.from_env()
    if settings.auth_mode not in {"demo", "members"}:
        raise ValueError("Unknown authentication mode")

    @asynccontextmanager
    async def lifespan(app):
        app.state.store = Store(settings) if settings.auth_mode == "demo" else None
        app.state.identity = IdentityRegistry(settings) if settings.auth_mode == "members" else None
        app.state.workspaces = WorkspaceStores(settings) if settings.auth_mode == "members" else None
        app.state.embeddings = embeddings or LocalEmbeddings(settings)
        app.state.answerer = answerer or GeminiAnswerer(settings)
        yield

    app = FastAPI(
        title="ClarityOps AI",
        version="0.3.0",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.add_middleware(RequestGuard, settings=settings,
                       authenticate=lambda token: app.state.identity.authenticate(token))
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Content-Type", "X-ClarityOps-Token"],
        allow_credentials=False,
    )

    def verify_actor(actor, owner=False):
        if owner and not actor.can_manage:
            raise AppError(403, "owner_required", "Only a workspace owner can perform this action.")
        if settings.auth_mode == "members":
            app.state.identity.require_active(actor, owner)

    def scoped_store(request):
        actor = request.state.principal
        verify_actor(actor)
        if settings.auth_mode == "demo":
            return app.state.store
        return app.state.workspaces.get(actor.workspace_id)

    def member_registry():
        if settings.auth_mode != "members":
            raise AppError(409, "members_mode_required", "Member access requires a provisioned company workspace.")
        return app.state.identity

    def error_response(request, status, code, message):
        request_id = getattr(request.state, "request_id", "unavailable")
        return JSONResponse(
            {"error": {"code": code, "message": message, "request_id": request_id}},
            status_code=status,
            headers={"Cache-Control": "no-store"},
        )

    @app.exception_handler(AppError)
    async def app_error(request, exc):
        if exc.status >= 500:
            logger.warning("request_error id=%s code=%s",
                           getattr(request.state, "request_id", "unavailable"), exc.code)
        return error_response(request, exc.status, exc.code, exc.message)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        return error_response(
            request, 422, "invalid_request", "Check the request fields and try again. Questions must contain 2–1500 characters."
        )

    @app.exception_handler(HTTPException)
    async def http_error(request, exc):
        return error_response(
            request, exc.status_code, "invalid_request", "The request could not be processed."
        )

    @app.exception_handler(Exception)
    async def unexpected_error(request, exc):
        logger.error(
            "request_failed id=%s type=%s",
            getattr(request.state, "request_id", "unavailable"),
            type(exc).__name__,
        )
        return error_response(
            request,
            500,
            "internal_error",
            "Something went wrong. Please retry or contact the workspace owner with the request ID.",
        )

    @app.get("/")
    def root():
        return {"message": "ClarityOps AI company knowledge assistant"}

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/status")
    def status(request: Request):
        actor = request.state.principal
        return {
            "gemini_configured": bool(settings.gemini_api_key),
            "embedding_files_present": (
                getattr(app.state.embeddings, "directory", settings.data_dir / "embedding-model")
                / "manifest.json"
            ).exists(),
            "workspace_mode": settings.auth_mode,
            "workspace": {"id": actor.workspace_id, "name": actor.workspace_name},
            "member": {"id": actor.member_id, "name": actor.name, "role": actor.role},
            "permissions": {"manage_documents": actor.can_manage,
                            "manage_members": actor.can_manage and settings.auth_mode == "members"},
            "max_file_mb": 10,
            "max_pages": settings.max_pages,
        }

    @app.get("/documents")
    def documents(request: Request):
        return {"documents": scoped_store(request).list_documents()}

    async def read_file(file):
        try:
            data = await file.read(settings.max_file_bytes + 1)
            name = validate_upload(file.filename, file.content_type, data, settings)
            return name, data
        finally:
            await file.close()

    def ingest(name, data, store, actor):
        duplicate = store.find_duplicate(data)
        if duplicate:
            return duplicate, True
        extracted = extract_pdf(data, settings)
        chunks = chunk_pages(extracted["pages"])
        if len(chunks) > settings.max_chunks:
            raise AppError(422, "too_many_chunks", "This document is too large to index.")
        vectors = app.state.embeddings.embed([c["text"] for c in chunks])
        verify_actor(actor, owner=True)
        warnings = []
        if extracted["blank_pages"]:
            warnings.append(
                "No text found on pages: "
                + ", ".join(map(str, extracted["blank_pages"]))
                + ". Those pages are not searchable."
            )
        return store.add_document(
            name, data, extracted["pages"], chunks, vectors, app.state.embeddings.model_id, warnings,
            actor_id=actor.member_id,
        )

    @app.post("/upload")
    async def upload(request: Request, file: UploadFile = File(...)):
        store = scoped_store(request)
        name, data = await read_file(file)
        document, duplicate = await run_in_threadpool(ingest, name, data, store, request.state.principal)
        return JSONResponse(
            {
                "document": document,
                "duplicate": duplicate,
                "filename": document["filename"],
                "message": "Already indexed" if duplicate else "Document indexed",
            },
            status_code=200 if duplicate else 201,
        )

    @app.post("/read-pdf")
    async def read_pdf(file: UploadFile = File(...)):
        name, data = await read_file(file)
        extracted = await run_in_threadpool(extract_pdf, data, settings)
        return {
            "filename": name,
            "pages": extracted["pages"],
            "blank_pages": extracted["blank_pages"],
            "text": "\n".join(p["text"] for p in extracted["pages"]),
        }

    @app.post("/ask")
    def ask(prompt: Prompt, request: Request):
        store = scoped_store(request)
        evidence = retrieve(prompt.prompt, store, app.state.embeddings, settings)
        if not evidence:
            return insufficient()
        verify_actor(request.state.principal)
        answer = app.state.answerer.answer(prompt.prompt, evidence)
        verify_actor(request.state.principal)
        # Recheck sources after generation in case they were deleted during the provider call.
        if not store.existing_ids({s["document_id"] for s in answer["sources"]}):
            return insufficient()
        return answer

    @app.delete("/documents/{document_id}")
    def delete_document(document_id: str, request: Request):
        store = scoped_store(request)
        verify_actor(request.state.principal, owner=True)
        store.delete(document_id, actor_id=request.state.principal.member_id)
        return Response(status_code=204)

    @app.get("/documents/{document_id}/file")
    def download_document(document_id: str, request: Request):
        name, data = scoped_store(request).document_file(document_id)
        verify_actor(request.state.principal)
        return Response(
            data,
            media_type="application/pdf",
            headers={
                "Content-Disposition": "attachment; filename*=UTF-8''" + quote(name, safe=""),
            },
        )

    @app.get("/members")
    def members(request: Request):
        return {"members": member_registry().list_members(request.state.principal)}

    @app.post("/members", status_code=201)
    def create_member(payload: NewMember, request: Request):
        return member_registry().add_member(request.state.principal, payload.name, payload.role,
                                             payload.expires_in_days)

    @app.delete("/members/{member_id}", status_code=204)
    def revoke_member(member_id: str, request: Request):
        member_registry().revoke(request.state.principal, member_id)
        return Response(status_code=204)

    @app.get("/audit")
    def audit(request: Request):
        verify_actor(request.state.principal, owner=True)
        events = scoped_store(request).events()
        if settings.auth_mode == "members":
            events += app.state.identity.events(request.state.principal)
        return {"events": sorted(events, key=lambda item: item["created_at"], reverse=True)[:100]}

    return app


app = create_app()
