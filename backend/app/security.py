import asyncio
import hmac
import logging
import threading
import time
import uuid
from collections import deque

from starlette.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from .identity import DEMO_PRINCIPAL


class RequestGuard:
    """Authenticate and bound body size BEFORE FastAPI's multipart parser runs."""

    def __init__(self, app, settings, authenticate=None):
        self.app, self.settings = app, settings
        self.authenticate = authenticate
        self.inflight = threading.BoundedSemaphore(4)
        self.requests = {}
        self.lock = threading.Lock()

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        request_id = uuid.uuid4().hex
        response_started = False
        scope.setdefault("state", {})["request_id"] = request_id
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope["headers"]}

        async def secure_send(message):
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
                message["headers"] = list(message["headers"]) + [
                    (b"cache-control", b"no-store"),
                    (b"x-content-type-options", b"nosniff"),
                    (b"x-request-id", request_id.encode()),
                ]
            await send(message)

        async def respond(status, code, message):
            await JSONResponse(
                {"error": {"code": code, "message": message, "request_id": request_id}}, status_code=status
            )(scope, receive, secure_send)

        if scope["path"] in ("/", "/health") and scope["method"] in ("GET", "HEAD"):
            return await self.app(scope, receive, secure_send)
        origin = headers.get("origin")
        if origin and origin not in self.settings.cors_origins:
            return await respond(403, "origin_denied", "This origin is not allowed.")
        if scope["method"] == "OPTIONS":
            return await self.app(scope, receive, secure_send)
        token = headers.get("x-clarityops-token", "")
        principal = None
        if self.settings.auth_mode == "members":
            try:
                if self.authenticate:
                    principal = await run_in_threadpool(self.authenticate, token)
            except Exception as exc:
                logging.getLogger("clarityops").error("authentication_failed type=%s", type(exc).__name__)
                return await respond(503, "authentication_unavailable", "Access verification is unavailable. Try again later.")
        elif self.settings.auth_mode == "demo":
            if not self.settings.access_token:
                return await respond(
                    503, "workspace_not_configured", "The workspace access token is not configured on the server."
                )
            if hmac.compare_digest(token.encode(), self.settings.access_token.encode()):
                principal = DEMO_PRINCIPAL
        if principal is None:
            return await respond(401, "unauthorized", "Enter a valid workspace access token to continue.")
        scope["state"]["principal"] = principal
        # Reject employee writes before reading or parsing even a single body byte.
        if not principal.can_manage and (
            scope["path"].split("/")[1] in {"members", "audit"}
            or (scope["method"] not in {"GET", "HEAD"} and not (
                scope["method"] == "POST" and scope["path"] == "/ask"
            ))
        ):
            return await respond(403, "owner_required", "Only a workspace owner can perform this action.")
        with self.lock:
            now = time.monotonic()
            requests = self.requests.setdefault(principal.workspace_id, deque())
            while requests and requests[0] < now - 60:
                requests.popleft()
            limited = len(requests) >= self.settings.requests_per_minute
            if not limited:
                requests.append(now)
        if limited:
            return await respond(429, "rate_limited", "Too many requests. Wait a minute and try again.")
        if not self.inflight.acquire(blocking=False):
            return await respond(429, "workspace_busy", "The workspace is busy. Please try again shortly.")
        try:
            limit = (
                self.settings.max_file_bytes + 64 * 1024
                if scope["path"] in ("/upload", "/read-pdf")
                else 16 * 1024
            )
            length = headers.get("content-length")
            if length:
                try:
                    if int(length) < 0:
                        raise ValueError()
                    if int(length) > limit:
                        return await respond(413, "request_too_large", "The upload or request is too large.")
                except ValueError:
                    return await respond(400, "invalid_length", "Invalid request length.")
            body = bytearray()
            deadline = time.monotonic() + 30
            while True:
                try:
                    message = await asyncio.wait_for(receive(), max(0.01, deadline - time.monotonic()))
                except TimeoutError:
                    return await respond(
                        408, "request_timeout", "The request took too long to upload. Please retry."
                    )
                if message["type"] == "http.disconnect":
                    return
                body.extend(message.get("body", b""))
                if len(body) > limit:
                    return await respond(413, "request_too_large", "The upload or request is too large.")
                if not message.get("more_body", False):
                    break
            delivered = False

            async def replay():
                nonlocal delivered
                if delivered:
                    return await receive()
                delivered = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}

            await self.app(scope, replay, secure_send)
        except Exception as exc:
            # Stop ServerErrorMiddleware/Uvicorn from printing an unredacted traceback.
            logging.getLogger("clarityops").error(
                "request_failed id=%s type=%s", request_id, type(exc).__name__
            )
            if response_started:
                raise RuntimeError("Response interrupted") from None
            await respond(
                500,
                "internal_error",
                "Something went wrong. Contact the workspace owner with the request ID.",
            )
        finally:
            self.inflight.release()
