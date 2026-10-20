from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from toolmeta_harvester.enrichment.input import (
    build_enrichment_input,
    enrichment_input_hash,
)
from toolmeta_harvester.enrichment.llm import EgiChatClient
from toolmeta_harvester.enrichment.pipeline import (
    extract_record,
    generate_record,
    validate_record,
)
from toolmeta_harvester.enrichment.prompts import extraction_v1, generation_v1
from toolmeta_harvester.enrichment.schemas import SemanticExtraction


class FakeClient:
    model = "test-model"

    def __init__(self, *responses):
        self.responses = list(responses)
        self.prompts = []

    def complete_json(self, system_prompt, user_prompt):
        self.prompts.append((system_prompt, user_prompt))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class MockResponse:
    def __init__(self, status, body):
        self.status_code = status
        self.ok = status < 400
        self.headers = {"Content-Type": "application/json"}
        self._body = body

    def json(self):
        return self._body


class MockSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def post(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return self.responses.pop(0)


def make_record(**overrides):
    values = {
        "id": "not-sent-to-llm",
        "metadata_format": "biotoolsSchema",
        "title": "Sequence aligner",
        "description": "Aligns short DNA sequences to a reference.",
        "raw_description": None,
        "keywords": ["alignment", "DNA"],
        "types": ["Command-line tool"],
        "software_types": [],
        "consumes_data": [],
        "produces_data": [],
        "inputs": [{"type": "File"}],
        "outputs": [],
        "raw_metadata": {
            "topic": [
                {"term": "Sequence analysis", "uri": "https://example.invalid/id"}
            ],
            "function": [{"operation": [{"term": "Sequence alignment"}]}],
            "owner": {"name": "not semantic"},
            "lastUpdate": "2026-01-01",
        },
        "enrichment_input_hash": None,
        "enrichment_status": "pending",
        "enrichment_failed_stage": None,
        "input_description": None,
        "output_description": None,
        "semantic_metadata": None,
        "enriched_description": None,
        "enrichment_validation": None,
        "enrichment_version": None,
        "enrichment_error": None,
        "enriched_at": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def make_enrichment(**overrides):
    values = {
        "input_hash": None,
        "status": "pending",
        "failed_stage": None,
        "input_description": None,
        "output_description": None,
        "semantic_metadata": None,
        "enriched_description": None,
        "validation": None,
        "extraction_model": None,
        "generation_model": None,
        "validation_model": None,
        "extraction_prompt_version": None,
        "generation_prompt_version": None,
        "validation_prompt_version": None,
        "error": None,
        "enriched_at": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def extraction_response():
    return {
        "input_description": "Short DNA sequences in file inputs, as stated in metadata.",
        "output_description": "Pairwise sequence alignments.",
        "supported_tasks": ["sequence alignment"],
        "methods_and_techniques": ["reference-based alignment"],
        "scientific_domains": ["bioinformatics"],
    }


def validation_response():
    return {
        "accuracy_score": 4,
        "completeness_score": 4,
        "input_quality_score": 3,
        "output_quality_score": 3,
        "enriched_description_score": 4,
        "semantic_usefulness_score": 4,
        "hallucination_detected": False,
        "issues": [],
        "overall_assessment": "Claims are supported by the metadata.",
    }


def test_enrichment_input_excludes_operational_raw_metadata_and_identity():
    record = make_record()
    payload = build_enrichment_input(record).model_dump(mode="json")
    assert "id" not in payload
    assert "metadata_format" not in payload
    assert "owner" not in payload["raw_semantic_metadata"]
    assert "lastUpdate" not in payload["raw_semantic_metadata"]
    assert "topic" in payload["raw_semantic_metadata"]
    assert "function" in payload["raw_semantic_metadata"]


def test_hash_is_deterministic_and_only_tracks_input_fields():
    first = make_record()
    second = make_record(id="different-id")
    digest = enrichment_input_hash(build_enrichment_input(first))
    assert digest == enrichment_input_hash(build_enrichment_input(second))
    second.description = "changed source description"
    assert digest != enrichment_input_hash(build_enrichment_input(second))


def test_prompt_rendering_is_versioned_and_contains_focused_metadata():
    prompt = extraction_v1.render_user_prompt(
        build_enrichment_input(make_record()).model_dump(mode="json")
    )
    assert extraction_v1.PROMPT_VERSION == "extraction_v1"
    assert "Sequence aligner" in prompt
    assert "lastUpdate" not in prompt
    generated_prompt = generation_v1.render_user_prompt(
        {"title": "Sequence aligner"}, {"supported_tasks": ["sequence alignment"]}
    )
    assert "sequence alignment" in generated_prompt


def test_structured_response_parsing_and_validation():
    client = EgiChatClient(api_key="test", retries=0)
    assert client._parse_json('```json\n{"value": 2}\n```') == {"value": 2}
    with pytest.raises(ValueError, match="malformed JSON|did not contain"):
        client._parse_json("not-json")
    with pytest.raises(ValidationError):
        SemanticExtraction.model_validate({"supported_tasks": "not a list"})


def test_egi_client_uses_mocked_api_and_retries_rate_limit():
    session = MockSession(
        [
            MockResponse(429, {}),
            MockResponse(
                200,
                {
                    "model": "actual-model",
                    "choices": [{"message": {"content": '{"ok": true}'}}],
                },
            ),
        ]
    )
    client = EgiChatClient(api_key="unit-test-token", retries=1, session=session)
    result = client.complete_json("system", "user")
    assert result.data == {"ok": True}
    assert result.requested_model == "qwen3.8-27b"
    assert result.actual_model == "actual-model"
    assert len(session.calls) == 2
    assert session.calls[0][1]["headers"]["Authorization"] == "Bearer unit-test-token"
    assert session.calls[0][1]["stream"] is True


def test_stage_transitions_and_prompt_versions():
    tool = make_record()
    record = make_enrichment()
    client = FakeClient(
        extraction_response(),
        {
            "enriched_description": "Aligns DNA sequences against a reference for bioinformatics."
        },
        validation_response(),
    )
    assert extract_record(tool, record, client)
    assert record.status == "extracted"
    assert record.extraction_prompt_version == "extraction_v1"
    assert record.extraction_model == "test-model"
    assert generate_record(tool, record, client)
    assert record.status == "generated"
    assert record.generation_prompt_version == "generation_v1"
    assert "Sequence aligner" in client.prompts[1][1]
    assert validate_record(tool, record, client)
    assert record.status == "validated"
    assert record.validation["accuracy_score"] == 4
    assert not extract_record(tool, record, client)


def test_failed_structured_response_sets_retryable_stage_state():
    tool = make_record()
    record = make_enrichment()
    with pytest.raises(ValidationError):
        extract_record(tool, record, FakeClient({"supported_tasks": "invalid"}))
    assert record.status == "failed"
    assert record.failed_stage == "extraction"
    assert record.error


def test_generation_failure_can_retry_without_losing_extraction():
    tool = make_record()
    record = make_enrichment()
    extract_record(tool, record, FakeClient(extraction_response()))
    original_hash = record.input_hash
    with pytest.raises(RuntimeError):
        generate_record(tool, record, FakeClient(RuntimeError("temporary failure")))
    assert record.status == "failed"
    assert record.failed_stage == "generation"
    assert record.input_hash == original_hash
    assert not extract_record(tool, record, FakeClient())
    assert generate_record(
        tool,
        record,
        FakeClient(
            {"enriched_description": "A metadata-grounded sequence alignment tool."}
        ),
    )
    assert record.status == "generated"


def test_prompt_version_change_reprocesses_unchanged_source_input():
    tool = make_record()
    record = make_enrichment()
    extract_record(tool, record, FakeClient(extraction_response()))
    original_hash = record.input_hash
    record.status = "validated"
    record.extraction_prompt_version = "extraction_v0"
    record.enriched_description = "Old prompt result"

    assert extract_record(tool, record, FakeClient(extraction_response()))
    assert record.input_hash == original_hash
    assert record.status == "extracted"
    assert record.enriched_description is None
