import logging
from contextlib import asynccontextmanager
from urllib.parse import quote

from fastapi import FastAPI, File, UploadFile
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
from .security import RequestGuard
from .store import Store

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


def create_app(settings=None, embeddings=None, answerer=None):
    settings = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(app):
        app.state.store = Store(settings)
        app.state.embeddings = embeddings or LocalEmbeddings(settings)
        app.state.answerer = answerer or GeminiAnswerer(settings)
        yield

    app = FastAPI(
        title="ClarityOps AI",
        version="0.2.0",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.add_middleware(RequestGuard, settings=settings)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Content-Type", "X-ClarityOps-Token"],
        allow_credentials=False,
    )

    def error_response(request, status, code, message):
        request_id = getattr(request.state, "request_id", "unavailable")
        return JSONResponse(
            {"error": {"code": code, "message": message, "request_id": request_id}},
            status_code=status,
            headers={"Cache-Control": "no-store"},
        )

    @app.exception_handler(AppError)
    async def app_error(request, exc):
        return error_response(request, exc.status, exc.code, exc.message)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        return error_response(
            request, 422, "invalid_request", "Provide a PDF file or a question between 2 and 1500 characters."
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
    def status():
        return {
            "gemini_configured": bool(settings.gemini_api_key),
            "embedding_files_present": (
                getattr(app.state.embeddings, "directory", settings.data_dir / "embedding-model")
                / "manifest.json"
            ).exists(),
            "workspace_mode": "single_company",
            "max_file_mb": 10,
            "max_pages": settings.max_pages,
        }

    @app.get("/documents")
    def documents():
        return {"documents": app.state.store.list_documents()}

    async def read_file(file):
        try:
            data = await file.read(settings.max_file_bytes + 1)
            name = validate_upload(file.filename, file.content_type, data, settings)
            return name, data
        finally:
            await file.close()

    def ingest(name, data):
        store = app.state.store
        duplicate = store.find_duplicate(data)
        if duplicate:
            return duplicate, True
        extracted = extract_pdf(data, settings)
        chunks = chunk_pages(extracted["pages"])
        if len(chunks) > settings.max_chunks:
            raise AppError(422, "too_many_chunks", "This document is too large to index.")
        vectors = app.state.embeddings.embed([c["text"] for c in chunks])
        warnings = []
        if extracted["blank_pages"]:
            warnings.append(
                "No text found on pages: "
                + ", ".join(map(str, extracted["blank_pages"]))
                + ". Those pages are not searchable."
            )
        return store.add_document(
            name, data, extracted["pages"], chunks, vectors, app.state.embeddings.model_id, warnings
        )

    @app.post("/upload")
    async def upload(file: UploadFile = File(...)):
        name, data = await read_file(file)
        document, duplicate = await run_in_threadpool(ingest, name, data)
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
    def ask(prompt: Prompt):
        evidence = retrieve(prompt.prompt, app.state.store, app.state.embeddings, settings)
        if not evidence:
            return insufficient()
        answer = app.state.answerer.answer(prompt.prompt, evidence)
        # Recheck sources after generation in case they were deleted during the provider call.
        if not app.state.store.existing_ids({s["document_id"] for s in answer["sources"]}):
            return insufficient()
        return answer

    @app.delete("/documents/{document_id}")
    def delete_document(document_id: str):
        app.state.store.delete(document_id)
        return Response(status_code=204)

    @app.get("/documents/{document_id}/file")
    def download_document(document_id: str):
        name, data = app.state.store.document_file(document_id)
        return Response(
            data,
            media_type="application/pdf",
            headers={
                "Content-Disposition": "attachment; filename*=UTF-8''" + quote(name, safe=""),
            },
        )

    return app


app = create_app()
