from __future__ import annotations

from typing import Any

from toolmeta_harvester.extractors.common import (
    TOOL_BASE_TYPES,
    as_list,
    extract_entity_metadata,
    local_type_name,
)
from toolmeta_harvester.extractors.jsonld import (
    get_jsonld_tool_entity,
)


BIOSCHEMAS_PROFILE_PREFIX = "https://bioschemas.org/profiles/"


def bioschemas_defines_tool(
    metadata: dict,
) -> bool:
    candidates = [metadata]

    graph = metadata.get("@graph")

    if isinstance(graph, list):
        candidates.extend(entity for entity in graph if isinstance(entity, dict))

    for entity in candidates:
        types = {
            local_type_name(str(type_id)) for type_id in as_list(entity.get("@type"))
        }

        if types & TOOL_BASE_TYPES:
            return True

    return False


def _conforms_to_values(
    metadata: dict[str, Any],
) -> list[str]:
    """
    Extract conformsTo/profile identifiers from common compact
    representations.
    """

    value = (
        metadata.get("http://purl.org/dc/terms/conformsTo")
        or metadata.get("dct:conformsTo")
        or metadata.get("conformsTo")
    )

    result = []

    for item in as_list(value):
        if isinstance(item, str):
            result.append(item)

        elif isinstance(item, dict):
            identifier = item.get("@id") or item.get("url")

            if identifier:
                result.append(str(identifier))

    return result


def is_bioschemas(
    metadata: dict[str, Any],
) -> bool:
    return any(
        value.startswith(BIOSCHEMAS_PROFILE_PREFIX)
        for value in _conforms_to_values(metadata)
    )


def get_bioschemas_profiles(
    metadata: dict[str, Any],
) -> list[str]:
    return [
        value
        for value in _conforms_to_values(metadata)
        if value.startswith(BIOSCHEMAS_PROFILE_PREFIX)
    ]


def extract_bioschemas_metadata(
    metadata: dict[str, Any],
) -> dict[str, Any]:
    """
    Convert Bioschemas JSON-LD into ScienceToolMeta.

    Bioschemas itself is a profile over Schema.org, so the common
    Schema.org extraction logic is reused.
    """

    entity = get_jsonld_tool_entity(metadata)

    if entity is None:
        raise ValueError("Bioschemas metadata does not describe a software tool")

    result = extract_entity_metadata(entity)

    result.update(
        {
            "metadata_type": "bioschemas",
            "metadata_version": None,
            "metadata_profile": (get_bioschemas_profiles(metadata)),
            "raw_metadata": metadata,
        }
    )

    return result
