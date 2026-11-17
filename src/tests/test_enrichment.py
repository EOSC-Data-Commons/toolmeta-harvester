from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from toolmeta_harvester.enrichment.input import (
    generation_input,
    has_source_metadata,
    input_hash,
)
from toolmeta_harvester.enrichment.llm import EgiChatClient
from toolmeta_harvester.enrichment.prompts import generation
from toolmeta_harvester.enrichment.schemas import GenerationResult


class MockResponse:
    def __init__(self, status: int, body: dict, headers: dict | None = None):
        self.status_code = status
        self.ok = status < 400
        self.headers = headers or {}
        self._body = body
        self.closed = False

    def json(self):
        return self._body

    def close(self):
        self.closed = True


class MockSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def post(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def test_generation_input_is_full_raw_metadata_and_hash_is_deterministic():
    raw_a = {"title": "A", "nested": {"private-field": [1, 2]}}
    raw_b = {"nested": {"private-field": [1, 2]}, "title": "A"}
    prompt_a = generation_input(raw_a)
    assert "private-field" in prompt_a
    assert input_hash(prompt_a) == input_hash(generation_input(raw_b))
    assert input_hash(prompt_a) != input_hash(generation_input({"title": "B"}))


def test_empty_metadata_is_distinguished_from_nonempty_values():
    assert not has_source_metadata({})
    assert not has_source_metadata([])
    assert not has_source_metadata("  ")
    assert has_source_metadata({"title": "Tool"})


def test_generation_response_status_and_description_constraints():
    assert (
        GenerationResult(status="generated", enriched_description="A tool.").status
        == "generated"
    )
    assert (
        GenerationResult(
            status="insufficient_metadata", enriched_description=None
        ).enriched_description
        is None
    )
    with pytest.raises(ValidationError):
        GenerationResult(status="generated", enriched_description=" ")
    with pytest.raises(ValidationError):
        GenerationResult(
            status="insufficient_metadata", enriched_description="Invented tool"
        )


def test_prompt_has_stable_id_and_version_and_disallows_invention():
    assert generation.PROMPT_ID == "tool-description-generation"
    assert generation.PROMPT_VERSION
    assert "Do not infer unsupported capabilities" in generation.SYSTEM_PROMPT


def test_llm_client_retries_rate_limit_and_records_actual_model(monkeypatch):
    monkeypatch.setattr("toolmeta_harvester.enrichment.llm.time.sleep", lambda _: None)
    session = MockSession(
        [
            MockResponse(429, {}, {"Retry-After": "0"}),
            MockResponse(
                200,
                {
                    "model": "actual-model",
                    "choices": [
                        {
                            "message": {
                                "content": '{"status":"generated","enriched_description":"Useful tool."}'
                            }
                        }
                    ],
                },
            ),
        ]
    )
    client = EgiChatClient(
        api_key="unit-test-token", model="requested-model", retries=1, session=session
    )
    result = client.complete_json(generation.SYSTEM_PROMPT, "raw metadata")
    assert result.data["status"] == "generated"
    assert result.requested_model == "requested-model"
    assert result.actual_model == "actual-model"
    assert result.request_count == 2
    assert len(session.calls) == 2
    assert session.calls[0][1]["headers"]["Authorization"] == "Bearer unit-test-token"
    assert session.calls[0][1]["json"]["model"] == "requested-model"


def test_llm_client_retries_malformed_json_and_rejects_permanent_http(monkeypatch):
    monkeypatch.setattr("toolmeta_harvester.enrichment.llm.time.sleep", lambda _: None)
    session = MockSession(
        [
            MockResponse(200, {"choices": [{"message": {"content": "not json"}}]}),
            MockResponse(
                200, {"choices": [{"message": {"content": json.dumps({"ok": True})}}]}
            ),
        ]
    )
    client = EgiChatClient(api_key="unit-test-token", retries=1, session=session)
    assert client.complete_json("system", "user").data == {"ok": True}
    assert client.last_request_count == 2

    permanent = EgiChatClient(
        api_key="unit-test-token",
        retries=3,
        session=MockSession([MockResponse(401, {})]),
    )
    with pytest.raises(RuntimeError, match="permanent HTTP 401"):
        permanent.complete_json("system", "user")
    assert permanent.last_request_count == 1


def test_llm_client_retries_structurally_invalid_generation(monkeypatch):
    monkeypatch.setattr("toolmeta_harvester.enrichment.llm.time.sleep", lambda _: None)
    session = MockSession(
        [
            MockResponse(
                200,
                {
                    "choices": [
                        {
                            "message": {
                                "content": '{"status":"generated","enriched_description":" "}'
                            }
                        }
                    ]
                },
            ),
            MockResponse(
                200,
                {
                    "choices": [
                        {
                            "message": {
                                "content": '{"status":"generated","enriched_description":"Useful tool."}'
                            }
                        }
                    ]
                },
            ),
        ]
    )
    client = EgiChatClient(api_key="unit-test-token", retries=1, session=session)
    result = client.complete_json(
        "system", "user", validator=GenerationResult.model_validate
    )
    assert result.data["enriched_description"] == "Useful tool."
    assert result.request_count == 2
