"""Canonical generation input and stable SHA-256 fingerprinting."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from toolmeta_harvester.enrichment.prompts.generation import render_user_prompt


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def generation_input(raw_metadata: Any) -> str:
    """Return the exact user-message content sent to the generation model."""
    return render_user_prompt(raw_metadata)


def input_hash(user_prompt: str) -> str:
    return hashlib.sha256(user_prompt.encode("utf-8")).hexdigest()


def has_source_metadata(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (dict, list, tuple, set)):
        return bool(value)
    return True
