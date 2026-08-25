from __future__ import annotations

from typing import Any

from toolmeta_harvester.extractors.description import clean_description


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []

    if isinstance(value, list):
        return value

    return [value]


def build_entity_index(crate: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """
    Index all JSON-LD entities in an RO-Crate by @id.
    """

    graph = crate.get("@graph", [])

    if not isinstance(graph, list):
        raise ValueError("Invalid RO-Crate: '@graph' must be a list")

    return {
        entity["@id"]: entity
        for entity in graph
        if isinstance(entity, dict) and isinstance(entity.get("@id"), str)
    }


def resolve(
    value: Any,
    entities: dict[str, dict[str, Any]],
) -> Any:
    """
    Resolve a JSON-LD reference against the RO-Crate entity index.

    Example:

        {"@id": "#python"}

    becomes the corresponding entity from @graph, if present.
    """

    if isinstance(value, dict) and "@id" in value:
        return entities.get(value["@id"], value)

    return value


def entity_value(
    value: Any,
    entities: dict[str, dict[str, Any]],
) -> Any:
    """
    Convert a JSON-LD reference/entity into a useful scalar value.

    Preference:
        name
        identifier
        @id
    """

    value = resolve(value, entities)

    if value is None:
        return None

    if isinstance(value, (str, int, float, bool)):
        return value

    if isinstance(value, dict):
        name = value.get("name")
        if name is not None:
            return name

        identifier = value.get("identifier")
        if identifier is not None:
            identifier = resolve(identifier, entities)

            if isinstance(identifier, dict):
                return (
                    identifier.get("@id")
                    or identifier.get("value")
                    or identifier.get("name")
                )

            return identifier

        return value.get("@id")

    return value


def extract_values(
    value: Any,
    entities: dict[str, dict[str, Any]],
) -> list[Any]:
    """
    Resolve one or more values into scalar representations.
    """

    values = []

    for item in as_list(value):
        resolved = entity_value(item, entities)

        if resolved is not None:
            values.append(resolved)

    return deduplicate_values(values)


def deduplicate_values(values: list[Any]) -> list[Any]:
    """
    Deduplicate scalar values while preserving order.
    """

    result = []
    seen = set()

    for value in values:
        try:
            key = value
            if key in seen:
                continue
            seen.add(key)
        except TypeError:
            # Non-hashable values are preserved.
            pass

        result.append(value)

    return result


def get_root_entity(
    crate: dict[str, Any],
    entities: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Return the RO-Crate Root Data Entity.

    Usually this is @id "./". As a fallback, use the metadata
    descriptor's `about` reference.
    """

    if entities is None:
        entities = build_entity_index(crate)

    root = entities.get("./")

    if root is not None:
        return root

    descriptor = entities.get("ro-crate-metadata.json")

    if descriptor:
        about = descriptor.get("about")
        resolved = resolve(about, entities)

        if isinstance(resolved, dict):
            return resolved

    raise ValueError("RO-Crate Root Data Entity could not be found")


def get_main_entity(
    root: dict[str, Any],
    entities: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    """
    Resolve the root entity's mainEntity.
    """

    main_entity = root.get("mainEntity")

    if not main_entity:
        return None

    resolved = resolve(main_entity, entities)

    if isinstance(resolved, dict):
        return resolved

    return None


def get_property(
    entity: dict[str, Any],
    *names: str,
) -> Any:
    """
    Return the first matching property.

    Useful for extension properties that may occur in compact or
    expanded forms.
    """

    for name in names:
        if name in entity:
            return entity[name]

    return None


def extract_people(
    value: Any,
    entities: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Convert Person/Organization references into canonical agent objects.
    """

    people = []

    for item in as_list(value):
        entity = resolve(item, entities)

        if isinstance(entity, str):
            people.append(
                {
                    "id": None,
                    "type": None,
                    "name": entity,
                    "identifier": None,
                    "orcid": None,
                    "url": None,
                }
            )
            continue

        if not isinstance(entity, dict):
            continue

        entity_id = entity.get("@id")
        identifier = entity.get("identifier")
        url = entity.get("url")

        if isinstance(identifier, dict):
            identifier = entity_value(identifier, entities)

        if isinstance(url, dict):
            url = entity_value(url, entities)

        orcid = None

        if isinstance(entity_id, str) and "orcid.org/" in entity_id:
            orcid = entity_id
        elif isinstance(identifier, str) and "orcid.org/" in identifier:
            orcid = identifier

        people.append(
            {
                "id": entity_id,
                "type": entity.get("@type"),
                "name": entity.get("name"),
                "identifier": identifier,
                "orcid": orcid,
                "url": url,
            }
        )

    return deduplicate_terms(people)


def extract_terms(
    value: Any,
    entities: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Convert schema.org/vocabulary values into canonical structured terms.

    Returned objects have the shape:

        {
            "id": ...,
            "name": ...,
            "alternate_name": ...,
            "identifier": ...,
            "url": ...
        }
    """

    terms = []

    for item in as_list(value):
        entity = resolve(item, entities)

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

        if not isinstance(entity, dict):
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

        identifier = entity.get("identifier")

        if isinstance(identifier, dict):
            identifier = entity_value(
                identifier,
                entities,
            )

        url = entity.get("url")

        if isinstance(url, dict):
            url = entity_value(
                url,
                entities,
            )

        terms.append(
            {
                "id": entity.get("@id"),
                "name": entity.get("name"),
                "alternate_name": entity.get("alternateName"),
                "identifier": identifier,
                "url": url,
            }
        )

    return deduplicate_terms(terms)


def deduplicate_terms(
    terms: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Deduplicate structured terms/agents while preserving order.
    """

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


def normalize_keywords(value: Any) -> list[str]:
    """
    Normalize schema:keywords to a list of strings.

    Supports:
        ["foo", "bar"]
        "foo, bar"
        "foo"
        ""
    """

    if value is None:
        return []

    if isinstance(value, str):
        value = value.strip()

        if not value:
            return []

        return [keyword.strip() for keyword in value.split(",") if keyword.strip()]

    keywords = []

    for item in as_list(value):
        if item is None:
            continue

        text = str(item).strip()

        if text:
            keywords.append(text)

    return deduplicate_values(keywords)


def normalize_identifiers(
    value: Any,
    entities: dict[str, dict[str, Any]],
) -> list[str]:
    """
    Normalize schema:identifier into string identifiers.
    """

    identifiers = []

    for item in as_list(value):
        resolved = resolve(item, entities)

        if resolved is None:
            continue

        if isinstance(resolved, str):
            identifiers.append(resolved)
            continue

        if isinstance(resolved, dict):
            identifier = (
                resolved.get("@id")
                or resolved.get("value")
                or resolved.get("identifier")
                or resolved.get("name")
            )

            if isinstance(identifier, dict):
                identifier = entity_value(
                    identifier,
                    entities,
                )

            if identifier is not None:
                identifiers.append(str(identifier))
            continue

        identifiers.append(str(resolved))

    return deduplicate_values(identifiers)


def get_rocrate_version(crate: dict[str, Any]) -> str | None:
    """
    Extract the RO-Crate specification version from the metadata
    descriptor's conformsTo property.

    Example:
        https://w3id.org/ro/crate/1.3
            -> 1.3
    """

    entities = build_entity_index(crate)

    descriptor = entities.get("ro-crate-metadata.json")

    if not descriptor:
        return None

    for item in as_list(descriptor.get("conformsTo")):
        resolved = item

        if isinstance(item, dict):
            resolved = item.get("@id")

        if not isinstance(resolved, str):
            continue

        prefix = "https://w3id.org/ro/crate/"

        if resolved.startswith(prefix):
            return resolved[len(prefix) :].rstrip("/")

    return None


def extract_profiles(
    crate: dict[str, Any],
) -> list[str]:
    """
    Return all profiles/specifications declared by the RO-Crate
    metadata descriptor.
    """

    entities = build_entity_index(crate)

    descriptor = entities.get("ro-crate-metadata.json")

    if not descriptor:
        return []

    profiles = []

    for item in as_list(descriptor.get("conformsTo")):
        if isinstance(item, dict):
            identifier = item.get("@id")
        else:
            identifier = item

        if identifier:
            profiles.append(str(identifier))

    return deduplicate_values(profiles)


def extract_programming_languages(
    main: dict[str, Any],
    entities: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Extract schema:programmingLanguage from the primary software entity.
    """

    return extract_terms(
        main.get("programmingLanguage"),
        entities,
    )


def extract_runtime_platforms(
    main: dict[str, Any],
    entities: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Extract schema:runtimePlatform.
    """

    return extract_terms(
        main.get("runtimePlatform"),
        entities,
    )


def extract_software_requirements(
    main: dict[str, Any],
    entities: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Extract schema:softwareRequirements.
    """

    return extract_terms(
        main.get("softwareRequirements"),
        entities,
    )


def extract_software_types(
    main: dict[str, Any],
    entities: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Extract software-types extension values.

    Supports a few likely compact representations so the extractor
    remains independent of the exact JSON-LD prefix used by the crate.
    """

    value = get_property(
        main,
        "softwareType",
        "stype:softwareType",
        "software-types:softwareType",
    )

    return extract_terms(
        value,
        entities,
    )


def extract_consumes_data(
    main: dict[str, Any],
    entities: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Extract software-iodata consumesData values.
    """

    value = get_property(
        main,
        "consumesData",
        "iodata:consumesData",
        "software-iodata:consumesData",
    )

    return extract_terms(
        value,
        entities,
    )


def extract_produces_data(
    main: dict[str, Any],
    entities: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Extract software-iodata producesData values.
    """

    value = get_property(
        main,
        "producesData",
        "iodata:producesData",
        "software-iodata:producesData",
    )

    return extract_terms(
        value,
        entities,
    )


def extract_ro_crate_metadata(
    crate: dict[str, Any],
) -> dict[str, Any]:
    """
    Convert an RO-Crate into the canonical ScienceToolMeta representation.

    The Root Data Entity provides crate-level metadata.

    If the crate defines mainEntity, that entity is treated as the primary
    scientific software/workflow entity and takes precedence for
    software-facing descriptive properties.
    """

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

    # -------------------------------------------------------------
    # Descriptive values
    # -------------------------------------------------------------

    raw_description = main.get("description") or root.get("description")

    authors = (
        main.get("author")
        or main.get("creator")
        or root.get("author")
        or root.get("creator")
    )

    license_value = main.get("license") or root.get("license")

    keywords = main.get("keywords") or root.get("keywords")

    identifiers = main.get("identifier") or root.get("identifier")

    # -------------------------------------------------------------
    # Canonical ScienceToolMeta
    # -------------------------------------------------------------

    return {
        # Core CodeMeta / schema.org metadata
        "title": (main.get("name") or root.get("name")),
        "description": clean_description(raw_description),
        "raw_description": raw_description,
        "version": (
            main.get("version")
            or main.get("softwareVersion")
            or root.get("version")
            or root.get("softwareVersion")
        ),
        "license": entity_value(
            license_value,
            entities,
        ),
        "identifiers": normalize_identifiers(
            identifiers,
            entities,
        ),
        "url": entity_value(
            main.get("url") or root.get("url"),
            entities,
        ),
        "code_repository": entity_value(
            main.get("codeRepository") or root.get("codeRepository"),
            entities,
        ),
        "keywords": normalize_keywords(keywords),
        "authors": extract_people(
            authors,
            entities,
        ),
        # RDF/schema types of the actual software entity
        "types": [
            str(value) for value in as_list(main.get("@type")) if value is not None
        ],
        # schema.org software metadata
        "programming_languages": (
            extract_programming_languages(
                main,
                entities,
            )
        ),
        "runtime_platforms": (
            extract_runtime_platforms(
                main,
                entities,
            )
        ),
        "software_requirements": (
            extract_software_requirements(
                main,
                entities,
            )
        ),
        # CodeMeta scientific extensions
        "software_types": extract_software_types(
            main,
            entities,
        ),
        "consumes_data": extract_consumes_data(
            main,
            entities,
        ),
        "produces_data": extract_produces_data(
            main,
            entities,
        ),
        # Dates
        "date_created": (main.get("dateCreated") or root.get("dateCreated")),
        "date_published": (main.get("datePublished") or root.get("datePublished")),
        "date_modified": (main.get("dateModified") or root.get("dateModified")),
        # Metadata representation
        "metadata_type": "ro-crate",
        "metadata_version": get_rocrate_version(crate),
        "metadata_profile": extract_profiles(crate),
        # Preserve complete source for provenance/reprocessing
        "raw_metadata": crate,
    }
