from __future__ import annotations

import re
from typing import Any

from toolmeta_harvester.extractors.common import (
    as_list,
    extract_entity_metadata,
    extract_io_entities,
    deduplicate_terms,
    deduplicate_values,
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


def extract_codemeta_inputs(
    metadata: dict[str, Any],
) -> list[dict[str, Any]]:
    inputs = []

    # Parameters directly on the root entity.
    inputs.extend(as_list(metadata.get("inputParameter")))

    # Parameters on applications or services described by the source code.
    for entity in as_list(metadata.get("isSourceCodeOf")):
        if isinstance(entity, dict):
            inputs.extend(as_list(entity.get("inputParameter")))

    return extract_io_entities(inputs)


def extract_codemeta_types(
    metadata: dict[str, Any],
) -> list[str]:
    types = as_list(metadata.get("@type"))

    types.extend(as_list(metadata.get("applicationCategory")))

    for entity in as_list(metadata.get("isSourceCodeOf")):
        if isinstance(entity, dict):
            types.extend(as_list(entity.get("@type")))

    return deduplicate_values([str(value) for value in types if value is not None])


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
            "types": extract_codemeta_types(metadata),
        }
    )
    result["inputs"] = deduplicate_terms(
        result["inputs"] + extract_codemeta_inputs(metadata)
    )

    return result
