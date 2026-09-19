import io

import numpy as np
import pytest
from fastapi.testclient import TestClient
from reportlab.pdfgen import canvas

from app.config import Settings
from app.gemini_service import Claim, GroundedResponse, insufficient, validate_answer
from app.main import create_app
from scripts.make_sample_pdf import make_pdf

TEST_TOKEN = "test-only-token-" + "x" * 40


class FakeEmbeddings:
    """Deterministic plumbing fixture. Real semantic quality has separate tests."""

    model_id = "test-embeddings-v1"

    def embed(self, texts, query=False):
        result = []
        for text in texts:
            vector = np.zeros(384, dtype="<f4")
            for i, term in enumerate(["leave", "expense", "sales", "laptop", "onboarding"]):
                vector[i] = float(term in text.lower())
            if not vector.any():
                vector[10] = 1
            result.append(vector / np.linalg.norm(vector))
        return np.array(result)


class EvidenceAnswerer:
    def answer(self, question, evidence):
        if "casual leave" not in question.lower():
            return insufficient()
        quote = "Employees receive 12 casual leave days per calendar year."
        for item in evidence:
            if quote in item["text"]:
                return validate_answer(
                    GroundedResponse(
                        supported=True, claims=[Claim(text=quote, source_id=item["source_id"], quote=quote)]
                    ),
                    evidence,
                )
        return insufficient()


def pdf_bytes(text="Employees receive 12 casual leave days per calendar year."):
    data = io.BytesIO()
    c = canvas.Canvas(data, invariant=1)
    if text:
        c.drawString(40, 700, text)
    c.showPage()
    c.save()
    return data.getvalue()


@pytest.fixture
def settings(tmp_path):
    return Settings(data_dir=tmp_path / "workspace", access_token=TEST_TOKEN, requests_per_minute=1000)


@pytest.fixture
def client(settings):
    with TestClient(
        create_app(settings, FakeEmbeddings(), EvidenceAnswerer()),
        raise_server_exceptions=False,
        headers={"X-ClarityOps-Token": TEST_TOKEN},
    ) as c:
        yield c


@pytest.fixture
def sample_pdf(tmp_path):
    return make_pdf(tmp_path / "Synthetic_Handbook.pdf").read_bytes()
