import io
import sqlite3
from dataclasses import replace
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfWriter

from app.documents import chunk_pages
from app.errors import AppError
from app.main import create_app
from conftest import TEST_TOKEN, FakeEmbeddings, EvidenceAnswerer, pdf_bytes


def upload(client, data, filename="Handbook.pdf", mime="application/pdf"):
    return client.post("/upload", files={"file": (filename, data, mime)})


def test_valid_ingestion_retrieval_citations_delete(client, sample_pdf, settings):
    response = upload(client, sample_pdf)
    assert response.status_code == 201, response.text
    doc = response.json()["document"]
    assert doc["page_count"] == 5 and doc["chunk_count"] >= 5
    assert doc["status"] == "ready"
    question = client.post("/ask", json={"prompt": "How many casual leave days do employees receive?"})
    assert question.status_code == 200
    result = question.json()
    assert result["status"] == "answered"
    assert "12" in result["answer"]
    assert result["sources"][0]["document_id"] == doc["id"]
    assert result["sources"][0]["page"] == 1
    assert result["sources"][0]["document"] == "Handbook.pdf"
    assert client.get(f"/documents/{doc['id']}/file").content == sample_pdf
    assert upload(client, sample_pdf, "renamed.pdf").json()["duplicate"] is True
    assert len(client.get("/documents").json()["documents"]) == 1
    assert client.delete(f"/documents/{doc['id']}").status_code == 204
    assert client.get(f"/documents/{doc['id']}/file").status_code == 404
    assert (
        client.post("/ask", json={"prompt": "casual leave days?"}).json()["status"] == "insufficient_evidence"
    )
    with sqlite3.connect(settings.data_dir / "knowledge.sqlite3") as db:
        assert db.execute("SELECT count(*) FROM chunks").fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM documents").fetchone()[0] == 0


def test_extract_preserves_pages_and_does_not_index(client, sample_pdf):
    r = client.post("/read-pdf", files={"file": ("Handbook.pdf", sample_pdf, "application/pdf")})
    assert r.status_code == 200
    assert [p["page"] for p in r.json()["pages"]] == [1, 2, 3, 4, 5]
    assert "12 casual leave" in r.json()["pages"][0]["text"]
    assert client.get("/documents").json()["documents"] == []


@pytest.mark.parametrize(
    "name,mime,data,status,code",
    [
        ("payload.txt", "text/plain", b"not a pdf", 415, "unsupported_file"),
        ("payload.pdf", "application/pdf", b"not a pdf", 415, "invalid_pdf"),
        ("payload.pdf", "application/pdf", b"%PDF-broken", 422, "malformed_pdf"),
        ("empty.pdf", "application/pdf", b"", 422, "empty_file"),
        ("../escape.pdf", "application/pdf", b"%PDF-", 400, "invalid_filename"),
    ],
)
@pytest.mark.parametrize("endpoint", ["/upload", "/read-pdf"])
def test_invalid_uploads(client, name, mime, data, status, code, endpoint):
    r = client.post(endpoint, files={"file": (name, data, mime)})
    assert r.status_code == status
    assert r.json()["error"]["code"] == code
    assert client.get("/documents").json()["documents"] == []


def test_blank_zero_page_and_encrypted(client):
    r = upload(client, pdf_bytes(""))
    assert r.status_code == 422 and r.json()["error"]["code"] == "no_extractable_text"
    empty = io.BytesIO()
    PdfWriter().write(empty)
    assert upload(client, empty.getvalue()).json()["error"]["code"] == "empty_document"
    writer = PdfWriter()
    writer.add_blank_page(200, 200)
    writer.encrypt("test-password")
    data = io.BytesIO()
    writer.write(data)
    assert upload(client, data.getvalue()).json()["error"]["code"] == "encrypted_pdf"


def test_duplicate_name_does_not_overwrite(client):
    assert upload(client, pdf_bytes()).status_code == 201
    assert upload(client, pdf_bytes("Expense claims need receipts.")).status_code == 409
    assert len(client.get("/documents").json()["documents"]) == 1


def test_oversize_file_and_body(client):
    r = upload(client, b"%PDF-" + b"x" * (10 * 1024 * 1024))
    assert r.status_code == 413
    r = client.post("/upload", content=b"x", headers={"Content-Length": str(11 * 1024 * 1024)})
    assert r.status_code == 413
    assert client.get("/documents").json()["documents"] == []


def test_page_limit(client):
    writer = PdfWriter()
    for _ in range(101):
        writer.add_blank_page(100, 100)
    data = io.BytesIO()
    writer.write(data)
    assert upload(client, data.getvalue()).json()["error"]["code"] == "too_many_pages"


def test_chunk_coverage_overlap_offsets():
    text = ("Company leave policy preserves employee eligibility. " * 150).strip()
    chunks = chunk_pages([{"page": 3, "text": text}, {"page": 4, "text": "Expense claims require receipts."}])
    page = [c for c in chunks if c["page"] == 3]
    assert len(page) > 5
    assert all(0 < len(c["text"]) <= 1000 for c in chunks)
    assert all(c["text"] == text[c["char_start"] : c["char_end"]] for c in page)
    assert all(a["char_end"] > b["char_start"] for a, b in zip(page, page[1:]))
    assert page[-1]["char_end"] == len(text)
    assert chunks[-1]["page"] == 4


def test_index_failure_is_atomic(client):
    with patch.object(
        client.app.state.embeddings,
        "embed",
        side_effect=AppError(503, "embedding_failed", "Search unavailable"),
    ):
        assert upload(client, pdf_bytes()).status_code == 503
    assert client.get("/documents").json()["documents"] == []


def test_restart_persists_documents(settings):
    for iteration in range(2):
        with TestClient(
            create_app(settings, FakeEmbeddings(), EvidenceAnswerer()),
            headers={"X-ClarityOps-Token": TEST_TOKEN},
        ) as c:
            if not iteration:
                assert upload(c, pdf_bytes()).status_code == 201
            assert len(c.get("/documents").json()["documents"]) == 1


def test_document_quota(settings):
    limited = replace(settings, max_documents=1)
    with TestClient(
        create_app(limited, FakeEmbeddings(), EvidenceAnswerer()), headers={"X-ClarityOps-Token": TEST_TOKEN}
    ) as c:
        assert upload(c, pdf_bytes()).status_code == 201
        assert (
            upload(c, pdf_bytes("Expense policy."), "Expense.pdf").json()["error"]["code"] == "workspace_full"
        )
