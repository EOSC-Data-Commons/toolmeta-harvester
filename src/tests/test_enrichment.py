from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from toolmeta_harvester.enrichment.input import build_enrichment_input
from toolmeta_harvester.enrichment.llm import EgiChatClient
from toolmeta_harvester.enrichment.pipeline import (
    _request_hash,
    content_hash,
    deterministic_validation,
    evaluate_description,
    extract_semantic_profile,
    generate_description,
    load_sample_ids,
)
from toolmeta_harvester.enrichment.prompts import extraction_v1
from toolmeta_harvester.enrichment.schemas import SemanticExtraction


class FakeClient:
    model = "test-model"
    last_request_count = 1
    last_elapsed_seconds = 0.01

    def __init__(self, response):
        self.response = response
        self.prompts = []

    def complete_json(self, system_prompt, user_prompt):
        self.prompts.append((system_prompt, user_prompt))
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


class MockResponse:
    def __init__(self, status, body):
        self.status_code = status
        self.ok = status < 400
        self.headers = {"Content-Type": "application/json"}
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
        self.headers = {}

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
        "inputs": [{"type": "FASTQ sequence", "format": "FASTQ"}],
        "outputs": [{"type": "Alignment", "format": "SAM"}],
        "raw_metadata": {
            "topic": [
                {"term": "Sequence analysis", "uri": "https://example.invalid/id"}
            ],
            "function": [{"operation": [{"term": "Sequence alignment"}]}],
            "owner": {"name": "not semantic"},
            "lastUpdate": "2026-01-01",
        },
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_enrichment_input_excludes_identity_and_operational_raw_metadata():
    payload = build_enrichment_input(make_record()).model_dump(mode="json")
    assert "id" not in payload
    assert "metadata_format" not in payload
    assert "owner" not in payload["raw_semantic_metadata"]
    assert "lastUpdate" not in payload["raw_semantic_metadata"]
    assert "topic" in payload["raw_semantic_metadata"]
    assert "function" in payload["raw_semantic_metadata"]


def test_canonical_hash_is_stable_and_tracks_content_not_mapping_order():
    assert content_hash({"b": 2, "a": 1}) == content_hash({"a": 1, "b": 2})
    assert _request_hash("model-a", "system", "user") == _request_hash(
        "model-a", "system", "user"
    )
    assert _request_hash("model-a", "system", "user") != _request_hash(
        "model-b", "system", "user"
    )
    assert _request_hash("model-a", "system", "user") != _request_hash(
        "model-a", "system", "changed"
    )


def test_extraction_returns_validated_semantic_profile_and_request_provenance():
    fake = FakeClient(
        {
            "input_description": "FASTQ DNA sequence files",
            "output_description": "SAM alignment records",
            "supported_tasks": ["sequence alignment"],
            "methods_and_techniques": ["reference-based alignment"],
            "scientific_domains": ["bioinformatics"],
        }
    )
    output = extract_semantic_profile(
        {"title": "Sequence aligner"}, client_factory=lambda **_: fake
    )
    assert output.data["supported_tasks"] == ["sequence alignment"]
    assert output.requested_model == "test-model"
    assert output.actual_model == "test-model"
    assert output.prompt_version == extraction_v1.PROMPT_VERSION
    assert len(output.input_hash) == 64
    assert output.request_count == 1


def test_generation_without_extraction_is_variant_a():
    fake = FakeClient(
        {"enriched_description": "Aligns DNA sequence reads to a reference."}
    )
    output = generate_description(
        {"title": "Sequence aligner"}, None, client_factory=lambda **_: fake
    )
    request = json.loads(fake.prompts[0][1].split("\n", 1)[1])
    assert request["extraction_used"] is False
    assert request["semantic_profile"] is None
    assert output.data["enriched_description"].startswith("Aligns DNA")
    assert output.actual_model == "test-model"


def test_generation_with_extraction_is_variant_b():
    profile = {
        "input_description": "FASTQ DNA sequence files",
        "output_description": "SAM alignments",
        "supported_tasks": ["sequence alignment"],
        "methods_and_techniques": ["reference-based alignment"],
        "scientific_domains": ["bioinformatics"],
    }
    fake = FakeClient(
        {"enriched_description": "Aligns FASTQ DNA reads and writes SAM records."}
    )
    output = generate_description(
        {"title": "Sequence aligner"}, profile, client_factory=lambda **_: fake
    )
    request = json.loads(fake.prompts[0][1].split("\n", 1)[1])
    assert request["extraction_used"] is True
    assert request["semantic_profile"] == profile
    assert output.data["enriched_description"]


def test_evaluation_records_structured_llm_judgment():
    response = {
        "accuracy_score": 4,
        "completeness_score": 4,
        "input_quality_score": 3,
        "output_quality_score": 3,
        "enriched_description_score": 4,
        "semantic_usefulness_score": 4,
        "hallucination_detected": False,
        "issues": [],
        "overall_assessment": "Claims are supported by the source metadata.",
    }
    output = evaluate_description(
        {"title": "Sequence aligner"},
        None,
        "Aligns DNA sequence reads to a reference.",
        requested_model="validator-v1",
        client_factory=lambda **_: FakeClient(response),
    )
    assert output.data["accuracy_score"] == 4
    assert output.requested_model == "test-model"
    assert output.prompt_version


def test_deterministic_validation_flags_empty_placeholders_and_artifacts():
    assert deterministic_validation("A useful scientific tool that aligns sequences.")[
        "passed"
    ]
    assert not deterministic_validation("")["passed"]
    assert not deterministic_validation("TODO: describe the tool later")["passed"]
    assert not deterministic_validation("```json\nA tool\n```")["passed"]


def test_response_schema_rejects_malformed_extraction():
    with pytest.raises(ValidationError):
        SemanticExtraction.model_validate({"supported_tasks": "not a list"})


def test_egi_client_retries_rate_limit_and_records_actual_model():
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
    client = EgiChatClient(
        api_key="unit-test-token",
        model="requested-model",
        retries=1,
        session=session,
    )
    result = client.complete_json("system", "user")
    assert result.data == {"ok": True}
    assert result.requested_model == "requested-model"
    assert result.actual_model == "actual-model"
    assert result.request_count == 2
    assert result.elapsed_seconds >= 0
    assert len(session.calls) == 2
    assert session.calls[0][1]["headers"]["Authorization"] == "Bearer unit-test-token"
    assert session.calls[0][1]["json"]["stream"] is False


def test_sample_loader_checks_fixed_size_unique_ids_and_hash(tmp_path):
    from uuid import uuid4

    ids = [str(uuid4()) for _ in range(100)]
    import hashlib

    sample = {
        "tool_ids": ids,
        "sample_sha256": hashlib.sha256("\n".join(ids).encode()).hexdigest(),
    }
    path = tmp_path / "sample.json"
    path.write_text(json.dumps(sample), encoding="utf-8")
    assert [str(value) for value in load_sample_ids(path)] == ids
    sample["tool_ids"][0] = sample["tool_ids"][1]
    path.write_text(json.dumps(sample), encoding="utf-8")
    with pytest.raises(ValueError, match="100 unique"):
        load_sample_ids(path)
