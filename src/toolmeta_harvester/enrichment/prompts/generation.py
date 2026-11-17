from __future__ import annotations

import json
from typing import Any

PROMPT_ID = "tool-description-generation"
PROMPT_VERSION = "1.0"
SYSTEM_PROMPT = """You write concise, factual discovery descriptions for research software and tools.
Use only facts supported by the supplied raw metadata. Do not infer unsupported capabilities,
audiences, scientific domains, inputs, outputs, or performance claims. If there is not enough
information to describe the tool reliably, return status=insufficient_metadata and no description.
Return one JSON object with keys status and enriched_description. status must be generated or
insufficient_metadata. Keep generated descriptions to 1-3 clear sentences."""


def render_user_prompt(raw_metadata: Any) -> str:
    canonical_metadata = json.dumps(raw_metadata, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "Create a discovery description from this raw metadata JSON.\n<raw_metadata>\n" + canonical_metadata + "\n</raw_metadata>"
