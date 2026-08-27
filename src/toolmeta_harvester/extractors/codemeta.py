from __future__ import annotations

import re
from typing import Any

from toolmeta_harvester.extractors.common import (
    extract_entity_metadata,
)


CODEMETA_PATTERN = re.compile(
    r"codemeta(?:/|@|:)?(?:v)?(\d+(?:\.\d+)*)?",
    re.IGNORECASE,
)


def _context_values(
    context: Any,
) -> list[str]:
    if context is None:
        return []

    if isinstance(context, str):
        return [context]

    if isinstance(context, list):
        result = []

        for value in context:
            result.extend(_context_values(value))

        return result

    if isinstance(context, dict):
        return [str(value) for value in context.values() if isinstance(value, str)]

    return []


def is_codemeta(
    metadata: dict[str, Any],
) -> bool:
    return any(
        "codemeta" in value.lower()
        for value in _context_values(metadata.get("@context"))
    )


def get_codemeta_version(
    metadata: dict[str, Any],
) -> str | None:
    for value in _context_values(metadata.get("@context")):
        match = CODEMETA_PATTERN.search(value)

        if match and match.group(1):
            return match.group(1)

    return None


def extract_codemeta_metadata(
    metadata: dict[str, Any],
) -> dict[str, Any]:
    result = extract_entity_metadata(metadata)

    result.update(
        {
            "metadata_type": "codemeta",
            "metadata_version": (get_codemeta_version(metadata)),
            "metadata_profile": [],
            "raw_metadata": metadata,
        }
    )

    return result
