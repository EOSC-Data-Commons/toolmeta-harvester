from __future__ import annotations

import json
from typing import Any

PROMPT_ID = "tool-description-validation"
PROMPT_VERSION = "1.0"
SYSTEM_PROMPT = """Assess whether a generated research-tool description is supported by its source metadata.
Return JSON with accuracy_score (0-5), completeness_score (0-5), hallucination_detected,
issues (array of concise strings), and overall_assessment. This is an advisory review only."""


def render_user_prompt(raw_metadata: Any, description: str) -> str:
    metadata = json.dumps(raw_metadata, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return f"Source raw metadata:\n{metadata}\n\nGenerated description:\n{description}"
