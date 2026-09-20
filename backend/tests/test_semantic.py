import os

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.embeddings import LocalEmbeddings, retrieve
from app.main import create_app
from conftest import TEST_TOKEN, EvidenceAnswerer
from test_ingestion import upload

pytestmark = [
    pytest.mark.semantic,
    pytest.mark.skipif(
        os.getenv("RUN_SEMANTIC_TESTS") != "1", reason="Set RUN_SEMANTIC_TESTS=1 after preparing embeddings"
    ),
]


@pytest.fixture(scope="module")
def real_embeddings():
    return LocalEmbeddings(Settings.from_env())


@pytest.mark.parametrize(
    "question,page",
    [
        ("How many casual leave days do employees receive?", 1),
        ("When is the deadline for submitting receipts for reimbursement?", 2),
        ("My work computer was stolen. Who do I tell?", 4),
        ("Who assigns a buddy to a new employee?", 5),
        ("What happens once a client signs the agreement?", 3),
    ],
)
def test_real_semantic_ranking(settings, sample_pdf, real_embeddings, question, page):
    with TestClient(
        create_app(settings, real_embeddings, EvidenceAnswerer()), headers={"X-ClarityOps-Token": TEST_TOKEN}
    ) as c:
        r = upload(c, sample_pdf)
        assert r.status_code == 201, r.text
        matches = retrieve(question, c.app.state.store, real_embeddings, settings)
        assert matches[0]["page"] == page
        assert matches[0]["score"] >= settings.retrieval_threshold


def test_unrelated_question_no_evidence(settings, sample_pdf, real_embeddings):
    with TestClient(create_app(settings, real_embeddings), headers={"X-ClarityOps-Token": TEST_TOKEN}) as c:
        upload(c, sample_pdf)
        r = c.post("/ask", json={"prompt": "What is the capital of France?"})
        assert r.status_code == 200
        assert r.json()["status"] == "insufficient_evidence"


def test_model_mismatch_fails_closed(settings, sample_pdf, real_embeddings):
    with TestClient(create_app(settings, real_embeddings), headers={"X-ClarityOps-Token": TEST_TOKEN}) as c:
        upload(c, sample_pdf)
        with c.app.state.store.connection() as db:
            db.execute("UPDATE chunks SET embedding_model='old-model'")
        r = c.post("/ask", json={"prompt": "How much casual leave do employees receive?"})
        assert r.status_code == 409


def test_missing_model_is_controlled(settings, sample_pdf):
    with TestClient(create_app(settings), headers={"X-ClarityOps-Token": TEST_TOKEN}) as c:
        r = upload(c, sample_pdf)
        assert r.status_code == 503 and r.json()["error"]["code"] == "embedding_unavailable"
        assert c.get("/documents").json()["documents"] == []


def test_real_retrieval_keeps_concurrent_company_evidence_separate(settings, real_embeddings):
    from concurrent.futures import ThreadPoolExecutor
    from dataclasses import replace
    from app.identity import IdentityRegistry
    from app.gemini_service import Claim, GroundedResponse, validate_answer
    from conftest import pdf_bytes

    config = replace(settings, auth_mode="members")
    registry = IdentityRegistry(config)
    a = registry.create_workspace("Synthetic Alpha", "Owner A")
    b = registry.create_workspace("Synthetic Beta", "Owner B")

    class QuoteAnswerer:
        def answer(self, question, evidence):
            source = evidence[0]
            return validate_answer(GroundedResponse(supported=True, claims=[
                Claim(text=source["text"], source_id=source["source_id"], quote=source["text"])
            ]), evidence)

    with TestClient(create_app(config, real_embeddings, QuoteAnswerer())) as c:
        cases = []
        for company, days in [(a, 12), (b, 23)]:
            auth = {"X-ClarityOps-Token": company["access_token"]}
            result = c.post("/upload", headers=auth, files={"file": (
                "Policy.pdf", pdf_bytes(f"Employees receive {days} casual leave days per calendar year."), "application/pdf")})
            assert result.status_code == 201
            cases.append((auth, days, result.json()["document"]["id"]))

        def ask(case):
            auth, days, doc_id = case
            result = c.post("/ask", json={"prompt": "How much casual leave is allowed?"}, headers=auth).json()
            assert result["status"] == "answered"
            assert f"{days} casual leave days" in result["answer"]
            assert {s["document_id"] for s in result["sources"]} == {doc_id}
            assert all(s["page"] == 1 for s in result["sources"])

        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(ask, cases * 3))
