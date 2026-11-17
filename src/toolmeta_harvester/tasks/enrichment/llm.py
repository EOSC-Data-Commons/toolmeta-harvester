import json
import httpx
from typing import Any

from toolmeta_harvester.tasks.enrichment.prompts.generation import (
    MODEL,
    SYSTEM_PROMPT,
)


def render_user_prompt(raw_metadata: Any) -> str:
    canonical_metadata = json.dumps(
        raw_metadata,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )

    return (
        "Generate a capability-oriented scientific software description "
        "from the following raw metadata:\n\n"
        f"<raw_metadata>\n{canonical_metadata}\n</raw_metadata>"
    )


async def enrich_tool_metadata(
    raw_metadata: Any,
    endpoint_url: str,
    api_key: str | None = None,
    timeout: float = 120.0,
) -> str | None:
    """Enrich tool metadata using an OpenAI-compatible LLM endpoint."""

    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": render_user_prompt(raw_metadata),
            },
        ],
        "temperature": 0.1,
        "max_tokens": 300,
        "stream": False,
    }

    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(
            # f"{endpoint_url.rstrip('/')}/chat/completions",
            f"{endpoint_url.rstrip('/')}",
            json=payload,
            headers=headers,
        )
        response.raise_for_status()

    data = response.json()
    description = data["choices"][0]["message"]["content"]

    if not isinstance(description, str):
        return None

    description = description.strip()

    return description or None
