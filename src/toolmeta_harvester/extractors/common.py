from __future__ import annotations

from collections.abc import Callable
from typing import Any
from urllib.parse import unquote

from toolmeta_harvester.extractors.description import (
    clean_description,
)


Resolver = Callable[[Any], Any]


TOOL_BASE_TYPES = {
    "SoftwareSourceCode",
    "SoftwareApplication",
    "ComputationalWorkflow",
    "ComputationalTool",
}


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []

    if isinstance(value, list):
        return value

    return [value]


def local_type_name(value: str) -> str:
    return value.rstrip("/").rsplit("/", 1)[-1].rsplit("#", 1)[-1]


def fallback_name_from_id(
    entity_id: str | None,
) -> str | None:
    if not entity_id:
        return None

    value = unquote(entity_id)

    if value.startswith("#"):
        value = value[1:]

    value = value.strip()

    return value or None


def identity(value: Any) -> Any:
    return value


def scalar_value(
    value: Any,
    resolver: Resolver = identity,
) -> str | None:
    """
    Resolve a value and reduce it to a useful scalar.
    """

    value = resolver(value)

    if value is None:
        return None

    if isinstance(value, str):
        return value

    if isinstance(value, (int, float, bool)):
        return str(value)

    if not isinstance(value, dict):
        return str(value)

    candidate = (
        value.get("name")
        or value.get("value")
        or value.get("identifier")
        or value.get("@id")
        or value.get("url")
    )

    if isinstance(candidate, dict):
        return scalar_value(
            candidate,
            resolver,
        )

    if candidate is None:
        return None

    return str(candidate)


def deduplicate_values(
    values: list[Any],
) -> list[Any]:
    result = []
    seen = set()

    for value in values:
        try:
            if value in seen:
                continue

            seen.add(value)

        except TypeError:
            pass

        result.append(value)

    return result


def deduplicate_terms(
    terms: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    result = []
    seen = set()

    for term in terms:
        key = (
            term.get("id")
            or term.get("identifier")
            or term.get("orcid")
            or term.get("url")
            or term.get("name")
        )

        if key is None:
            result.append(term)
            continue

        key = str(key)

        if key in seen:
            continue

        seen.add(key)
        result.append(term)

    return result


def normalize_keywords(
    value: Any,
) -> list[str]:
    if value is None:
        return []

    if isinstance(value, str):
        value = value.strip()

        if not value:
            return []

        return deduplicate_values(
            [keyword.strip() for keyword in value.split(",") if keyword.strip()]
        )

    result = []

    for item in as_list(value):
        if item is None:
            continue

        if isinstance(item, dict):
            text = scalar_value(item)
        else:
            text = str(item)

        if text:
            text = text.strip()

        if text:
            result.append(text)

    return deduplicate_values(result)


def normalize_identifiers(
    value: Any,
    resolver: Resolver = identity,
) -> list[str]:
    identifiers = []

    for item in as_list(value):
        item = resolver(item)

        identifier = scalar_value(
            item,
            resolver,
        )

        if identifier:
            identifiers.append(identifier)

    return deduplicate_values(identifiers)


def person_name(
    entity: dict[str, Any],
) -> str | None:
    name = entity.get("name")

    if name:
        return str(name)

    given_name = entity.get("givenName")
    family_name = entity.get("familyName")

    parts = [
        str(value).strip()
        for value in (
            given_name,
            family_name,
        )
        if value
    ]

    if parts:
        return " ".join(parts)

    return fallback_name_from_id(entity.get("@id"))


def extract_people(
    value: Any,
    resolver: Resolver = identity,
) -> list[dict[str, Any]]:
    people = []

    for item in as_list(value):
        entity = resolver(item)

        if isinstance(entity, str):
            people.append(
                {
                    "id": None,
                    "type": None,
                    "name": fallback_name_from_id(entity),
                    "given_name": None,
                    "family_name": None,
                    "identifier": None,
                    "orcid": None,
                    "url": None,
                }
            )
            continue

        if not isinstance(entity, dict):
            continue

        entity_id = entity.get("@id")

        identifier = scalar_value(
            entity.get("identifier"),
            resolver,
        )

        url = scalar_value(
            entity.get("url"),
            resolver,
        )

        orcid = None

        for candidate in (
            entity_id,
            identifier,
            url,
        ):
            if isinstance(candidate, str) and "orcid.org/" in candidate:
                orcid = candidate
                break

        people.append(
            {
                "id": entity_id,
                "type": entity.get("@type"),
                "name": person_name(entity),
                "given_name": scalar_value(
                    entity.get("givenName"),
                    resolver,
                ),
                "family_name": scalar_value(
                    entity.get("familyName"),
                    resolver,
                ),
                # "name": (entity.get("name") or fallback_name_from_id(entity_id)),
                "identifier": identifier,
                "orcid": orcid,
                "url": url,
            }
        )

    return deduplicate_terms(people)


def extract_organization(
    value: Any,
    resolver: Resolver = identity,
) -> dict[str, Any] | None:
    entity = resolver(value)

    if not entity:
        return None

    if isinstance(entity, str):
        return {
            "id": None,
            "name": entity,
            "url": None,
        }

    if not isinstance(entity, dict):
        return None

    types = {local_type_name(str(type_id)) for type_id in as_list(entity.get("@type"))}

    if types and "Organization" not in types and "Project" not in types:
        return None

    return {
        "id": entity.get("@id"),
        "name": entity.get("name"),
        "url": scalar_value(
            entity.get("url"),
            resolver,
        ),
    }


def extract_organizations(
    *values: Any,
    resolver: Resolver = identity,
) -> list[dict[str, Any]]:
    organizations = []

    for value in values:
        for item in as_list(value):
            organization = extract_organization(
                item,
                resolver,
            )

            if organization:
                organizations.append(organization)

    return deduplicate_terms(organizations)


def extract_terms(
    value: Any,
    resolver: Resolver = identity,
) -> list[dict[str, Any]]:
    terms = []

    for item in as_list(value):
        entity = resolver(item)

        if entity is None:
            continue

        if isinstance(entity, str):
            terms.append(
                {
                    "id": None,
                    "name": entity,
                    "alternate_name": None,
                    "identifier": None,
                    "url": None,
                }
            )
            continue

        if isinstance(
            entity,
            (int, float, bool),
        ):
            terms.append(
                {
                    "id": None,
                    "name": str(entity),
                    "alternate_name": None,
                    "identifier": None,
                    "url": None,
                }
            )
            continue

        if not isinstance(entity, dict):
            continue

        terms.append(
            {
                "id": entity.get("@id"),
                "name": entity.get("name"),
                "alternate_name": entity.get("alternateName"),
                "identifier": scalar_value(
                    entity.get("identifier"),
                    resolver,
                ),
                "url": scalar_value(
                    entity.get("url"),
                    resolver,
                ),
            }
        )

    return deduplicate_terms(terms)


def extract_io_entities(
    value: Any,
    resolver: Resolver = identity,
) -> list[dict[str, Any]]:
    results = []

    for item in as_list(value):
        entity = resolver(item)

        if isinstance(entity, str):
            results.append(
                {
                    "id": None,
                    "name": entity,
                    "description": None,
                    "type": [],
                    "additional_type": None,
                    "encoding_format": None,
                }
            )
            continue

        if not isinstance(entity, dict):
            continue

        results.append(
            {
                "id": entity.get("@id"),
                "name": entity.get("name"),
                "description": clean_description(entity.get("description")),
                "type": [
                    str(type_id)
                    for type_id in as_list(entity.get("@type"))
                    if type_id is not None
                ],
                "additional_type": scalar_value(
                    entity.get("additionalType"),
                    resolver,
                ),
                "encoding_format": scalar_value(
                    entity.get("encodingFormat"),
                    resolver,
                ),
            }
        )

    return deduplicate_terms(results)


def get_property(
    entity: dict[str, Any],
    *names: str,
) -> Any:
    for name in names:
        if name in entity:
            return entity[name]

    return None


def extract_entity_metadata(
    primary: dict[str, Any],
    *,
    fallback: dict[str, Any] | None = None,
    resolver: Resolver = identity,
) -> dict[str, Any]:
    """
    Extract canonical ScienceToolMeta fields from a schema.org-like
    software entity.

    `primary` is normally:
        - RO-Crate mainEntity
        - CodeMeta root object
        - generic JSON-LD software entity

    `fallback` is normally the RO-Crate Root Data Entity.
    """

    fallback = fallback or {}

    raw_description = primary.get("description") or fallback.get("description")

    authors = (
        primary.get("author")
        or primary.get("creator")
        or fallback.get("author")
        or fallback.get("creator")
    )

    license_value = primary.get("license") or fallback.get("license")

    keywords = primary.get("keywords") or fallback.get("keywords")

    identifiers = primary.get("identifier") or fallback.get("identifier")

    software_types = get_property(
        primary,
        "softwareType",
        "stype:softwareType",
        "software-types:softwareType",
    ) or get_property(
        fallback,
        "softwareType",
        "stype:softwareType",
        "software-types:softwareType",
    )

    consumes_data = get_property(
        primary,
        "consumesData",
        "iodata:consumesData",
        "software-iodata:consumesData",
    ) or get_property(
        fallback,
        "consumesData",
        "iodata:consumesData",
        "software-iodata:consumesData",
    )

    produces_data = get_property(
        primary,
        "producesData",
        "iodata:producesData",
        "software-iodata:producesData",
    ) or get_property(
        fallback,
        "producesData",
        "iodata:producesData",
        "software-iodata:producesData",
    )

    return {
        "title": (primary.get("name") or fallback.get("name")),
        "description": clean_description(raw_description),
        "raw_description": raw_description,
        "version": (
            primary.get("version")
            or primary.get("softwareVersion")
            or fallback.get("version")
            or fallback.get("softwareVersion")
        ),
        "license": scalar_value(
            license_value,
            resolver,
        ),
        "identifiers": normalize_identifiers(
            identifiers,
            resolver,
        ),
        "url": scalar_value(
            primary.get("url") or fallback.get("url"),
            resolver,
        ),
        "code_repository": scalar_value(
            primary.get("codeRepository") or fallback.get("codeRepository"),
            resolver,
        ),
        "keywords": normalize_keywords(keywords),
        "authors": extract_people(
            authors,
            resolver,
        ),
        "organizations": extract_organizations(
            primary.get("producer"),
            primary.get("publisher"),
            primary.get("provider"),
            primary.get("affiliation"),
            fallback.get("producer"),
            fallback.get("publisher"),
            fallback.get("provider"),
            fallback.get("affiliation"),
            resolver=resolver,
        ),
        "types": [
            str(type_id)
            for type_id in as_list(primary.get("@type"))
            if type_id is not None
        ],
        "programming_languages": extract_terms(
            primary.get("programmingLanguage") or fallback.get("programmingLanguage"),
            resolver,
        ),
        "runtime_platforms": extract_terms(
            primary.get("runtimePlatform") or fallback.get("runtimePlatform"),
            resolver,
        ),
        "software_requirements": extract_terms(
            primary.get("softwareRequirements") or fallback.get("softwareRequirements"),
            resolver,
        ),
        "software_types": extract_terms(
            software_types,
            resolver,
        ),
        "consumes_data": extract_terms(
            consumes_data,
            resolver,
        ),
        "produces_data": extract_terms(
            produces_data,
            resolver,
        ),
        "inputs": extract_io_entities(
            primary.get("input") or fallback.get("input"),
            resolver,
        ),
        "outputs": extract_io_entities(
            primary.get("output") or fallback.get("output"),
            resolver,
        ),
        "date_created": (primary.get("dateCreated") or fallback.get("dateCreated")),
        "date_published": (
            primary.get("datePublished") or fallback.get("datePublished")
        ),
        "date_modified": (primary.get("dateModified") or fallback.get("dateModified")),
    }
