from __future__ import annotations

from typing import Any

from toolmeta_harvester.extractors.common import (
    TOOL_BASE_TYPES,
    as_list,
    extract_entity_metadata,
    local_type_name,
)


def jsonld_defines_tool(
    metadata: dict[str, Any],
) -> bool:
    entity = get_jsonld_tool_entity(metadata)

    return entity is not None


def is_tool_entity(
    entity: dict[str, Any],
) -> bool:
    return any(
        local_type_name(str(type_id)) in TOOL_BASE_TYPES
        for type_id in as_list(entity.get("@type"))
    )


def get_jsonld_tool_entity(
    metadata: dict[str, Any],
) -> dict[str, Any] | None:
    """
    Find the software entity in generic JSON-LD.

    Supports both a flat object and a generic @graph.
    """

    if is_tool_entity(metadata):
        return metadata

    graph = metadata.get("@graph")

    if not isinstance(graph, list):
        return None

    for entity in graph:
        if isinstance(entity, dict) and is_tool_entity(entity):
            return entity

    return None


def extract_jsonld_metadata(
    metadata: dict[str, Any],
) -> dict[str, Any]:
    entity = get_jsonld_tool_entity(metadata)

    if entity is None:
        raise ValueError("JSON-LD does not describe a software tool")

    result = extract_entity_metadata(entity)

    result.update(
        {
            "metadata_type": "json-ld",
            "metadata_version": None,
            "metadata_profile": [],
            "raw_metadata": metadata,
        }
    )

    return result
