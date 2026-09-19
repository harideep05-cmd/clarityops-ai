import json
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient

from app.errors import AppError
from app.gemini_service import GeminiAnswerer, GroundedResponse, validate_answer
from app.main import create_app
from conftest import TEST_TOKEN, FakeEmbeddings, pdf_bytes
from test_ingestion import upload

EVIDENCE = [
    {
        "source_id": "S1",
        "id": "abc:0",
        "document_id": "abc",
        "filename": "Policy.pdf",
        "page": 2,
        "text": "Employees receive 12 casual leave days per calendar year.",
        "char_start": 0,
        "char_end": 55,
    }
]
VALID = {
    "supported": True,
    "claims": [
        {
            "text": "Employees receive 12 casual leave days per calendar year.",
            "source_id": "S1",
            "quote": EVIDENCE[0]["text"],
        }
    ],
}


def mock_client(result=None, error=None):
    client = Mock()
    client.__enter__ = Mock(return_value=client)
    client.__exit__ = Mock(return_value=False)
    if error:
        client.models.generate_content.side_effect = error
    else:
        client.models.generate_content.return_value = SimpleNamespace(text=result)
    return client


def test_provider_contract_and_grounded_generation(settings):
    client = mock_client(json.dumps(VALID))
    with patch("app.gemini_service.genai.Client", return_value=client):
        r = GeminiAnswerer(replace(settings, gemini_api_key="test-only-placeholder")).answer(
            "How many casual leave days?", EVIDENCE
        )
    assert r["status"] == "answered" and r["sources"][0]["page"] == 2
    args = client.models.generate_content.call_args.kwargs
    payload = json.loads(args["contents"])
    assert payload["question"] == "How many casual leave days?"
    assert payload["evidence"][0]["text"] == EVIDENCE[0]["text"]
    assert "test-only-placeholder" not in args["contents"]
    assert "untrusted" in args["config"].system_instruction
    assert args["config"].response_schema is GroundedResponse


@pytest.mark.parametrize(
    "mutation", ["unknown_source", "invented_quote", "wrong_number", "unsupported", "no_claims"]
)
def test_bad_grounding_fails_closed(mutation):
    data = json.loads(json.dumps(VALID))
    if mutation == "unknown_source":
        data["claims"][0]["source_id"] = "S999"
    elif mutation == "invented_quote":
        data["claims"][0]["quote"] = "Employees receive unlimited leave."
    elif mutation == "wrong_number":
        data["claims"][0]["text"] = "Employees receive 99 days."
    elif mutation == "unsupported":
        data["supported"] = False
    else:
        data["claims"] = []
    result = validate_answer(GroundedResponse(**data), EVIDENCE)
    assert result["status"] == "insufficient_evidence"
    assert result["sources"] == []


def test_missing_key_is_controlled_and_upload_still_works(settings):
    with TestClient(create_app(settings, FakeEmbeddings()), headers={"X-ClarityOps-Token": TEST_TOKEN}) as c:
        assert c.get("/health").status_code == 200
        assert upload(c, pdf_bytes()).status_code == 201
        r = c.post("/ask", json={"prompt": "How many casual leave days?"})
        assert r.status_code == 503
        assert r.json()["error"]["code"] == "provider_not_configured"


@pytest.mark.parametrize(
    "result", ["", "not json", '{"supported": true}', '{"supported":true,"claims":[],"extra":"bad"}']
)
def test_invalid_provider_response(settings, result):
    with patch("app.gemini_service.genai.Client", return_value=mock_client(result)):
        with pytest.raises(AppError) as exc:
            GeminiAnswerer(replace(settings, gemini_api_key="test-key")).answer("leave?", EVIDENCE)
    assert exc.value.status == 502


@pytest.mark.parametrize("error", [TimeoutError("sensitive content"), RuntimeError("secret credential")])
def test_provider_errors_are_sanitized(settings, error, caplog):
    with patch("app.gemini_service.genai.Client", return_value=mock_client(error=error)):
        with pytest.raises(AppError) as exc:
            GeminiAnswerer(replace(settings, gemini_api_key="test-key")).answer("private question", EVIDENCE)
    assert exc.value.status == 502
    assert str(error) not in caplog.text
    assert "private question" not in caplog.text
    assert str(error) not in exc.value.message


def test_unsupported_question_and_empty_workspace(client):
    assert client.post("/ask", json={"prompt": "How many casual leave days?"}).json()["sources"] == []
    assert upload(client, pdf_bytes()).status_code == 201
    result = client.post("/ask", json={"prompt": "What is our parental leave allowance?"}).json()
    assert result["status"] == "insufficient_evidence" and result["sources"] == []


def test_provider_http_failure(settings):
    config = replace(settings, gemini_api_key="test-only-key")
    with TestClient(create_app(config, FakeEmbeddings()), headers={"X-ClarityOps-Token": TEST_TOKEN}) as c:
        upload(c, pdf_bytes())
        with patch(
            "app.gemini_service.genai.Client",
            return_value=mock_client(error=RuntimeError("private exception")),
        ):
            r = c.post("/ask", json={"prompt": "casual leave?"})
        assert r.status_code == 502 and "private exception" not in r.text


def test_concurrent_deletion_invalidates_answer(client):
    doc = upload(client, pdf_bytes()).json()["document"]
    original = client.app.state.answerer.answer

    def deleting_answer(question, evidence):
        result = original(question, evidence)
        client.app.state.store.delete(doc["id"])
        return result

    with patch.object(client.app.state.answerer, "answer", side_effect=deleting_answer):
        assert (
            client.post("/ask", json={"prompt": "casual leave?"}).json()["status"] == "insufficient_evidence"
        )


def test_whitespace_quote_cannot_pass_attribution():
    data = json.loads(json.dumps(VALID))
    data["claims"][0]["quote"] = " " * 10
    data["claims"][0]["text"] = "Unlimited leave is allowed."
    assert validate_answer(GroundedResponse(**data), EVIDENCE)["status"] == "insufficient_evidence"
