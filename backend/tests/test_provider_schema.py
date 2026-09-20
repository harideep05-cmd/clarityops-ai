"""Provider compatibility tests use the real SDK with an offline HTTP transport."""

import json
from copy import deepcopy
from dataclasses import replace
from unittest.mock import patch

import httpx
import pytest
from google import genai

from app.errors import AppError
from app.gemini_service import GeminiAnswerer, GroundedResponse, parse_provider_response
from test_answers import EVIDENCE, VALID, mock_client


@pytest.mark.parametrize(
    "change",
    [
        "top_extra", "claim_extra", "missing_supported", "missing_claims", "missing_text",
        "missing_source", "missing_quote", "claims_object", "claims_string", "claims_null",
        "claim_string", "claim_list", "claim_null", "supported_string", "supported_number",
        "supported_null", "text_number", "quote_null", "source_number", "too_many_claims",
    ],
)
def test_provider_structure_fails_closed(settings, change):
    value = deepcopy(VALID)
    if change == "top_extra":
        value["private_field"] = "synthetic-sensitive-value"
    elif change == "claim_extra":
        value["claims"][0]["private_field"] = "synthetic-sensitive-value"
    elif change.startswith("missing_"):
        key = change.removeprefix("missing_")
        target = value if key in {"supported", "claims"} else value["claims"][0]
        target.pop("source_id" if key == "source" else key)
    elif change.startswith("claims_"):
        value["claims"] = {"object": {}, "string": "bad", "null": None}[change[7:]]
    elif change.startswith("claim_"):
        value["claims"] = [{"string": "bad", "list": [], "null": None}[change[6:]]]
    elif change.startswith("supported_"):
        value["supported"] = {"string": "true", "number": 1, "null": None}[change[10:]]
    elif change == "text_number":
        value["claims"][0]["text"] = 12
    elif change == "quote_null":
        value["claims"][0]["quote"] = None
    elif change == "source_number":
        value["claims"][0]["source_id"] = 1
    else:
        value["claims"] *= 7
    with patch("app.gemini_service.genai.Client", return_value=mock_client(json.dumps(value))):
        with pytest.raises(AppError) as caught:
            GeminiAnswerer(replace(settings, gemini_api_key="synthetic-test-key")).answer("leave?", EVIDENCE)
    assert caught.value.status == 502
    assert caught.value.code == "provider_invalid_response"
    assert "synthetic-sensitive-value" not in caught.value.message


@pytest.mark.parametrize(
    "text",
    [
        "{", "[]", "null", "true", "12", '"text"',
        '{"supported":true,"claims":[]} trailing',
        '{"supported":false,"supported":true,"claims":[]}',
        '{"supported":true,"claims":[{"text":"one","text":"two"}]}',
        '{"supported":NaN,"claims":[]}',
        '{"supported":Infinity,"claims":[]}',
        "x" * (128 * 1024 + 1),
    ],
    ids=["incomplete", "array", "null", "boolean", "number", "string", "trailing",
         "duplicate_top", "duplicate_claim", "nan", "infinity", "oversized"],
)
def test_invalid_json_and_ambiguous_fields(text):
    with pytest.raises(ValueError):
        parse_provider_response(text)


def assert_compatible_schema(value):
    if isinstance(value, dict):
        assert "additionalProperties" not in value
        assert "additional_properties" not in value
        for child in value.values():
            assert_compatible_schema(child)
    elif isinstance(value, list):
        for child in value:
            assert_compatible_schema(child)


@pytest.mark.parametrize("status", [200, 429])
def test_actual_sdk_wire_schema_and_quota_handling_without_network(settings, status, caplog):
    requests = []

    def handler(request):
        requests.append(json.loads(request.content))
        if status == 429:
            return httpx.Response(429, json={"error": {"code": 429, "status": "RESOURCE_EXHAUSTED",
                                                      "message": "synthetic-private-provider-detail"}})
        return httpx.Response(200, json={"candidates": [{"content": {"role": "model", "parts": [
            {"text": json.dumps(VALID)}]}, "finishReason": "STOP"}]})

    actual_client = genai.Client

    def offline_client(**kwargs):
        kwargs["http_options"].client_args = {"transport": httpx.MockTransport(handler), "trust_env": False}
        return actual_client(**kwargs)

    with patch("app.gemini_service.genai.Client", side_effect=offline_client):
        answerer = GeminiAnswerer(replace(settings, gemini_api_key="synthetic-offline-key"))
        if status == 200:
            answer = answerer.answer("How many casual leave days?", EVIDENCE)
            assert answer["status"] == "answered"
            assert answer["sources"][0]["page"] == 2
        else:
            with pytest.raises(AppError) as caught:
                answerer.answer("How many casual leave days?", EVIDENCE)
            assert (caught.value.status, caught.value.code) == (503, "provider_rate_limited")
            assert "synthetic-private-provider-detail" not in caught.value.message + caplog.text
    assert len(requests) == 1  # Never retry exhausted provider quota automatically.
    schema = requests[0]["generationConfig"]["responseSchema"]
    assert_compatible_schema(schema)
    assert_compatible_schema(GroundedResponse.model_json_schema())
    assert set(schema["required"]) == {"supported", "claims"}


def test_valid_refusal_and_answer_are_accepted():
    assert parse_provider_response(json.dumps(VALID)).supported is True
    refusal = parse_provider_response('{"supported":false,"claims":[]}')
    assert refusal.supported is False and refusal.claims == []
