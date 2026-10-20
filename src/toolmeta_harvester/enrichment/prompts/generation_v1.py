from __future__ import annotations

import json

PROMPT_VERSION = "generation_v1"
SYSTEM_PROMPT = """Write one concise, factual enriched description to support scientific tool discovery and
future tool–dataset matching. Ground every statement in the supplied metadata and extracted
profile. Cover what the tool does, supported tasks, methods, inputs, outputs, and scientific
contexts only when known. Never infer formats or capabilities from generic types such as File.
Avoid marketing language, filler, repetition, and unsupported claims. Return only JSON:
{"enriched_description": "..."}."""


def render_user_prompt(metadata: dict, extraction: dict) -> str:
    return "Metadata and validated extracted profile:\n" + json.dumps(
        {"metadata": metadata, "semantic_profile": extraction},
        ensure_ascii=False,
        sort_keys=True,
        indent=2,
    )
