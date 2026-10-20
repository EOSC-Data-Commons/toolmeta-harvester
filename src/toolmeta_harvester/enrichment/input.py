from __future__ import annotations

import hashlib
import json
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

RAW_SEMANTIC_KEYS = {
    "application",
    "component",
    "datatype",
    "datatypes",
    "filepattern",
    "format",
    "function",
    "input",
    "inputs",
    "method",
    "methods",
    "operation",
    "output",
    "outputs",
    "parameter",
    "patterns",
    "step",
    "steps",
    "task",
    "term",
    "tooltype",
    "topic",
    "type",
    "name",
    "label",
    "text",
    "value",
    "workflow",
}
MAX_RAW_SEMANTIC_CHARS = 8000


class EnrichmentInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = None
    description: str | None = None
    raw_description: str | None = None
    keywords: list[str] = Field(default_factory=list)
    types: list[str] = Field(default_factory=list)
    software_types: list[dict[str, Any]] = Field(default_factory=list)
    consumes_data: list[dict[str, Any]] = Field(default_factory=list)
    produces_data: list[dict[str, Any]] = Field(default_factory=list)
    inputs: list[dict[str, Any]] = Field(default_factory=list)
    outputs: list[dict[str, Any]] = Field(default_factory=list)
    raw_semantic_metadata: dict[str, Any] = Field(default_factory=dict)


def _raw_key_is_semantic(key: str) -> bool:
    return (
        "".join(char for char in key.casefold() if char.isalnum()) in RAW_SEMANTIC_KEYS
    )


def _select_raw(value: Any, *, depth: int = 0) -> Any:
    if depth > 5:
        return None
    if isinstance(value, dict):
        selected = {}
        for key, item in value.items():
            normalized_key = "".join(
                char for char in str(key).casefold() if char.isalnum()
            )
            if _raw_key_is_semantic(str(key)):
                pruned = _select_raw(item, depth=depth + 1)
                if pruned not in (None, "", [], {}):
                    selected[str(key)] = pruned
            elif normalized_key in {"data", "attributes", "workflow", "content"}:
                nested = _select_raw(item, depth=depth + 1)
                if nested not in (None, "", [], {}):
                    selected[str(key)] = nested
        return selected
    if isinstance(value, list):
        return [
            item
            for raw in value[:100]
            if (item := _select_raw(raw, depth=depth + 1)) not in (None, "", [], {})
        ]
    if isinstance(value, str):
        return value[:1000]
    if isinstance(value, (int, float, bool)):
        return value
    return None


def build_enrichment_input(record: Any) -> EnrichmentInput:
    """Build focused semantic input without operational/source identity fields."""
    raw = _select_raw(getattr(record, "raw_metadata", None) or {})
    raw_metadata = raw if isinstance(raw, dict) else {}
    # Cap pathological source payloads before hashing or sending them to the API.
    encoded = json.dumps(raw_metadata, ensure_ascii=False, sort_keys=True)
    if len(encoded) > MAX_RAW_SEMANTIC_CHARS:
        raw_metadata = {}

    values = {
        field: getattr(record, field, None)
        for field in EnrichmentInput.model_fields
        if field != "raw_semantic_metadata"
    }
    return EnrichmentInput(**values, raw_semantic_metadata=raw_metadata)


def enrichment_input_hash(enrichment_input: EnrichmentInput) -> str:
    payload = json.dumps(
        enrichment_input.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
