from __future__ import annotations

from typing import Any
from urllib.parse import quote, unquote

from toolmeta_harvester.extractors.common import (
    TOOL_BASE_TYPES,
    as_list,
    deduplicate_values,
    extract_entity_metadata,
    local_type_name,
)


def is_ro_crate(
    metadata: dict[str, Any],
) -> bool:
    graph = metadata.get("@graph")

    if not isinstance(graph, list):
        return False

    return any(
        isinstance(entity, dict)
        and entity.get("@id")
        in {
            "ro-crate-metadata.json",
            "ro-crate-metadata.jsonld",
        }
        for entity in graph
    )


def build_entity_index(
    crate: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    entities = {}

    for entity in crate.get("@graph", []):
        if not isinstance(entity, dict):
            continue

        entity_id = entity.get("@id")

        if not isinstance(entity_id, str):
            continue

        entities[entity_id] = entity

        entities.setdefault(
            unquote(entity_id),
            entity,
        )

        entities.setdefault(
            quote(
                entity_id,
                safe="#/:?=&",
            ),
            entity,
        )

    return entities


def resolve(
    value: Any,
    entities: dict[str, dict[str, Any]],
) -> Any:
    if not isinstance(value, dict) or "@id" not in value:
        return value

    entity_id = value["@id"]

    for candidate in (
        entity_id,
        unquote(entity_id),
        quote(
            entity_id,
            safe="#/:?=&",
        ),
    ):
        if candidate in entities:
            return entities[candidate]

    return value


def get_root_entity(
    crate: dict[str, Any],
    entities: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    root = entities.get("./")

    if root is not None:
        return root

    descriptor = entities.get("ro-crate-metadata.json") or entities.get(
        "ro-crate-metadata.jsonld"
    )

    if descriptor:
        root = resolve(
            descriptor.get("about"),
            entities,
        )

        if isinstance(root, dict):
            return root

    raise ValueError("RO-Crate Root Data Entity could not be found")


def get_main_entity(
    root: dict[str, Any],
    entities: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    main = root.get("mainEntity")

    if not main:
        return None

    main = resolve(
        main,
        entities,
    )

    if isinstance(main, dict):
        return main

    return None


def is_subclass_of(
    type_id: str,
    entities: dict[str, dict[str, Any]],
    visited: set[str] | None = None,
) -> bool:
    if local_type_name(type_id) in TOOL_BASE_TYPES:
        return True

    if visited is None:
        visited = set()

    if type_id in visited:
        return False

    visited.add(type_id)

    entity = resolve(
        {"@id": type_id},
        entities,
    )

    if not isinstance(entity, dict):
        return False

    parents = entity.get("rdfs:subClassOf") or entity.get("subClassOf")

    return any(
        is_subclass_of(
            str(parent.get("@id") if isinstance(parent, dict) else parent),
            entities,
            visited,
        )
        for parent in as_list(parents)
        if parent
    )


def ro_crate_defines_tool(
    crate: dict[str, Any],
) -> bool:
    entities = build_entity_index(crate)

    root = get_root_entity(
        crate,
        entities,
    )

    main = get_main_entity(
        root,
        entities,
    )

    candidate = main or root

    return any(
        is_subclass_of(
            str(type_id),
            entities,
        )
        for type_id in as_list(candidate.get("@type"))
    )


def get_rocrate_version(
    crate: dict[str, Any],
) -> str | None:
    entities = build_entity_index(crate)

    descriptor = entities.get("ro-crate-metadata.json") or entities.get(
        "ro-crate-metadata.jsonld"
    )

    if not descriptor:
        return None

    prefix = "https://w3id.org/ro/crate/"

    for item in as_list(descriptor.get("conformsTo")):
        value = item.get("@id") if isinstance(item, dict) else item

        if isinstance(value, str) and value.startswith(prefix):
            return value[len(prefix) :].rstrip("/")

    return None


def extract_profiles(
    crate: dict[str, Any],
) -> list[str]:
    entities = build_entity_index(crate)

    descriptor = entities.get("ro-crate-metadata.json") or entities.get(
        "ro-crate-metadata.jsonld"
    )

    if not descriptor:
        return []

    return deduplicate_values(
        [
            str(item.get("@id") if isinstance(item, dict) else item)
            for item in as_list(descriptor.get("conformsTo"))
            if item
        ]
    )


def extract_ro_crate_metadata(
    crate: dict[str, Any],
) -> dict[str, Any]:
    entities = build_entity_index(crate)

    root = get_root_entity(
        crate,
        entities,
    )

    main = (
        get_main_entity(
            root,
            entities,
        )
        or root
    )

    def resolver(value: Any) -> Any:
        return resolve(
            value,
            entities,
        )

    result = extract_entity_metadata(
        main,
        fallback=root,
        resolver=resolver,
    )

    result.update(
        {
            "metadata_type": "ro-crate",
            "metadata_version": (get_rocrate_version(crate)),
            "metadata_profile": (extract_profiles(crate)),
            "raw_metadata": crate,
        }
    )

    return result
