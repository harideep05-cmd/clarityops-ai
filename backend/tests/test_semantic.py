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
