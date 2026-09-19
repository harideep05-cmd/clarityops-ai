import asyncio
from dataclasses import replace
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.documents import extract_pdf, validate_upload
from app.errors import AppError
from app.main import create_app
from app.security import RequestGuard
from conftest import TEST_TOKEN, FakeEmbeddings, EvidenceAnswerer, pdf_bytes
from test_ingestion import upload


def test_auth_applies_to_all_private_routes(settings):
    with TestClient(create_app(settings, FakeEmbeddings())) as c:
        assert c.get("/health").status_code == 200
        for method, path in [
            ("GET", "/documents"),
            ("GET", "/status"),
            ("POST", "/upload"),
            ("POST", "/ask"),
            ("POST", "/read-pdf"),
            ("DELETE", "/documents/x"),
            ("GET", "/documents/x/file"),
        ]:
            assert c.request(method, path).status_code == 401
        assert c.get("/documents", headers={"X-ClarityOps-Token": "wrong"}).status_code == 401


def test_unconfigured_workspace_denies_data(settings):
    with TestClient(create_app(replace(settings, access_token=""))) as c:
        assert c.get("/health").status_code == 200
        assert c.get("/documents").status_code == 503


def test_cors_and_cache(client):
    r = client.get("/documents", headers={"Origin": "https://untrusted.example"})
    assert r.status_code == 403
    assert "access-control-allow-origin" not in r.headers
    r = client.options(
        "/ask",
        headers={
            "Origin": "http://127.0.0.1:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "x-clarityops-token,content-type",
        },
    )
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == "http://127.0.0.1:5173"
    assert client.get("/documents").headers["cache-control"] == "no-store"
    assert client.get("/documents").headers["x-content-type-options"] == "nosniff"


@pytest.mark.parametrize(
    "payload",
    [
        {"prompt": "   "},
        {"prompt": "x" * 1501},
        {"question": "leave?"},
        {"prompt": "leave?", "tenant_id": "other"},
    ],
)
def test_invalid_questions(client, payload):
    r = client.post("/ask", json=payload)
    assert r.status_code == 422
    assert "input" not in r.text


def test_separate_workspaces_cannot_read_each_other(settings, tmp_path):
    other = replace(settings, data_dir=tmp_path / "other", access_token="other-" + TEST_TOKEN)
    with (
        TestClient(
            create_app(settings, FakeEmbeddings(), EvidenceAnswerer()),
            headers={"X-ClarityOps-Token": TEST_TOKEN},
        ) as a,
        TestClient(
            create_app(other, FakeEmbeddings(), EvidenceAnswerer()),
            headers={"X-ClarityOps-Token": other.access_token},
        ) as b,
    ):
        doc = upload(a, pdf_bytes()).json()["document"]
        assert b.get("/documents").json()["documents"] == []
        assert b.get(f"/documents/{doc['id']}/file").status_code == 404
        assert b.delete(f"/documents/{doc['id']}").status_code == 404
        assert b.get("/documents", headers={"X-ClarityOps-Token": TEST_TOKEN}).status_code == 401


def test_streamed_body_limit_without_content_length(settings):
    called = False

    async def downstream(scope, receive, send):
        nonlocal called
        called = True

    guard = RequestGuard(downstream, settings)
    messages = iter(
        [
            {"type": "http.request", "body": b"x" * 9000, "more_body": True},
            {"type": "http.request", "body": b"x" * 9000, "more_body": False},
        ]
    )
    sent = []

    async def receive():
        return next(messages)

    async def send(message):
        sent.append(message)

    asyncio.run(
        guard(
            {
                "type": "http",
                "method": "POST",
                "path": "/ask",
                "headers": [(b"x-clarityops-token", TEST_TOKEN.encode())],
            },
            receive,
            send,
        )
    )
    assert not called
    assert sent[0]["status"] == 413


def test_parser_timeout_is_controlled(settings):
    import subprocess

    with patch("app.documents.subprocess.run", side_effect=subprocess.TimeoutExpired("parser", 20)):
        with pytest.raises(AppError) as exc:
            extract_pdf(pdf_bytes(), settings)
    assert exc.value.code == "extraction_timeout"


def test_windows_filename_never_becomes_path(client, settings):
    with pytest.raises(AppError):
        validate_upload("C:\\escape.pdf", "application/pdf", pdf_bytes(), settings)
    # python-multipart normalizes browser-supplied Windows paths before our handler.
    r = upload(client, pdf_bytes(), "C:\\escape.pdf")
    assert r.status_code == 201
    assert r.json()["document"]["filename"] == "escape.pdf"
    assert not (settings.data_dir / "escape.pdf").exists()  # content is a SQLite blob


def test_rate_limit(settings):
    with TestClient(
        create_app(replace(settings, requests_per_minute=1)), headers={"X-ClarityOps-Token": TEST_TOKEN}
    ) as c:
        assert c.get("/documents").status_code == 200
        assert c.get("/documents").status_code == 429
        assert c.get("/health").status_code == 200


def test_unexpected_exception_is_sanitized_before_server_logs(client, caplog):
    with patch.object(
        client.app.state.store, "list_documents", side_effect=RuntimeError("sensitive payload")
    ):
        r = client.get("/documents")
    assert r.status_code == 500
    assert "sensitive payload" not in r.text + caplog.text
    assert r.json()["error"]["request_id"]


def test_pdf_worker_does_not_receive_application_secrets(settings, monkeypatch):
    from types import SimpleNamespace

    monkeypatch.setenv("GEMINI_API_KEY", "synthetic-worker-secret")
    monkeypatch.setenv("GOOGLE_API_KEY", "synthetic-worker-secret")
    monkeypatch.setenv("CLARITYOPS_ACCESS_TOKEN", TEST_TOKEN)
    result = SimpleNamespace(
        returncode=0, stdout=b'{"pages": [{"page":1,"text":"Policy"}], "blank_pages": []}'
    )
    with patch("app.documents.subprocess.run", return_value=result) as run:
        extract_pdf(pdf_bytes(), settings)
    env = run.call_args.kwargs["env"]
    assert all(key not in env for key in ["GEMINI_API_KEY", "GOOGLE_API_KEY", "CLARITYOPS_ACCESS_TOKEN"])


def test_private_directory_permissions_even_after_model_setup(settings):
    import os
    import stat
    from app.store import Store

    if os.name == "nt":
        pytest.skip("POSIX permission semantics; Windows ACL review remains required")
    settings.data_dir.mkdir(mode=0o755)
    store = Store(settings)
    assert stat.S_IMODE(settings.data_dir.stat().st_mode) == 0o700
    assert stat.S_IMODE(store.path.stat().st_mode) == 0o600
