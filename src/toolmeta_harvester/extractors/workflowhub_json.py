from __future__ import annotations

from typing import Any

from toolmeta_harvester.extractors.description import (
    clean_description,
)


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []

    if isinstance(value, list):
        return value

    return [value]


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


def make_term(
    name: str | None,
    *,
    id: str | None = None,
    type: list[str] | None = None,
    alternate_name: str | None = None,
    identifier: str | None = None,
    url: str | None = None,
) -> dict[str, Any] | None:
    """
    Create a canonical JSON-LD-like term matching common.extract_terms().
    """
    if not name and not id and not identifier and not url:
        return None

    return {
        "id": id,
        "type": type or [],
        "name": name,
        "alternate_name": alternate_name,
        "identifier": identifier,
        "url": url,
    }


def extract_workflowhub_types(
    value: Any,
) -> list[str]:
    """
    Extract WorkflowHub internal parameter types.

    Examples:

        [{"type": "File"}]     -> ["File"]
        [{"type": "File[]"}]   -> ["File[]"]
        [{"type": "string?"}]  -> ["string?"]
    """
    result: list[str] = []

    for item in as_list(value):
        if isinstance(item, str):
            result.append(item)
            continue

        if not isinstance(item, dict):
            continue

        type_value = item.get("type")

        if type_value is not None:
            result.append(str(type_value))

    return result


def extract_io_entities(
    value: Any,
) -> list[dict[str, Any]]:
    """
    Convert WorkflowHub internals inputs/outputs to the canonical
    I/O structure used by common.extract_io_entities().
    """
    results: list[dict[str, Any]] = []

    for item in as_list(value):
        if not isinstance(item, dict):
            continue

        results.append(
            {
                "id": item.get("id"),
                "name": item.get("name"),
                "description": clean_description(item.get("description")),
                "type": extract_workflowhub_types(item.get("type")),
                "additional_type": None,
                "encoding_format": None,
                "value_required": None,
                "default_value": item.get("default_value"),
            }
        )

    return deduplicate_terms(results)


def extract_authors(
    value: Any,
) -> list[dict[str, Any]]:
    """
    Convert WorkflowHub creators to the canonical person structure
    returned by common.extract_people().
    """
    results: list[dict[str, Any]] = []

    for creator in as_list(value):
        if not isinstance(creator, dict):
            continue

        given_name = creator.get("given_name")
        family_name = creator.get("family_name")

        name = " ".join(
            str(part).strip()
            for part in (
                given_name,
                family_name,
            )
            if part
        )

        orcid = creator.get("orcid")

        results.append(
            {
                "id": (orcid if orcid else None),
                "type": "Person",
                "name": name or None,
                "given_name": given_name,
                "family_name": family_name,
                "identifier": orcid,
                "orcid": orcid,
                "url": orcid,
            }
        )

    return deduplicate_terms(results)


def get_latest_version(
    attributes: dict[str, Any],
) -> dict[str, Any] | None:
    latest_version = attributes.get("latest_version")

    if latest_version is None:
        return None

    for version in as_list(attributes.get("versions")):
        if not isinstance(version, dict):
            continue

        if str(version.get("version")) == str(latest_version):
            return version

    return None


def extract_identifiers(
    attributes: dict[str, Any],
    meta: dict[str, Any],
) -> list[str]:
    identifiers: list[str] = []

    doi = attributes.get("doi")

    if doi:
        identifiers.append(str(doi))

    uuid = meta.get("uuid")

    if uuid:
        identifiers.append(str(uuid))

    return list(dict.fromkeys(identifiers))


def extract_workflow_tools(
    value: Any,
) -> list[dict[str, Any]]:
    """
    Convert WorkflowHub tool annotations into canonical terms.

    Example:

        {
            "name": "STAR",
            "id": "https://bio.tools/star"
        }

    becomes:

        {
            "id": "https://bio.tools/star",
            "type": [],
            "name": "STAR",
            "alternate_name": None,
            "identifier": None,
            "url": "https://bio.tools/star",
        }
    """
    results = []

    for item in as_list(value):
        if not isinstance(item, dict):
            continue

        tool_id = item.get("id")

        term = make_term(
            item.get("name"),
            id=tool_id,
            url=tool_id,
        )

        if term:
            results.append(term)

    return deduplicate_terms(results)


def extract_workflowhub_metadata(
    document: dict[str, Any],
) -> dict[str, Any]:
    """
    Extract canonical metadata from the WorkflowHub JSON API.

    Example endpoint:

        https://workflowhub.org/workflows/401.json

    The returned structure matches the canonical structures produced
    by extractors.common where possible.
    """
    data = document.get("data") or {}

    if not isinstance(data, dict):
        data = {}

    attributes = data.get("attributes") or {}

    if not isinstance(
        attributes,
        dict,
    ):
        attributes = {}

    meta = data.get("meta") or {}

    if not isinstance(
        meta,
        dict,
    ):
        meta = {}

    internals = attributes.get("internals") or {}

    if not isinstance(
        internals,
        dict,
    ):
        internals = {}

    workflow_class = attributes.get("workflow_class") or {}

    if not isinstance(
        workflow_class,
        dict,
    ):
        workflow_class = {}

    latest_version = get_latest_version(attributes)

    workflow_class_title = workflow_class.get("title")

    workflow_class_key = workflow_class.get("key")

    #
    # Types remain strings, because this matches common.py:
    #
    #     "types": [
    #         str(type_id)
    #         for type_id in as_list(primary.get("@type"))
    #     ]
    #
    types = [
        "ComputationalWorkflow",
    ]

    if workflow_class_title:
        types.append(str(workflow_class_title))

    #
    # JSON-LD-style workflow class term.
    #
    workflow_class_term = make_term(
        (str(workflow_class_title) if workflow_class_title else None),
        identifier=(str(workflow_class_key) if workflow_class_key else None),
    )

    runtime_platforms = []

    if workflow_class_term:
        runtime_platforms.append(workflow_class_term)

    #
    # Galaxy, CWL, Nextflow etc. are also useful as
    # software/workflow classification terms.
    #
    software_types = []

    if workflow_class_term:
        software_types.append(workflow_class_term.copy())

    code_repository = None
    workflow_url = None

    if latest_version:
        code_repository = latest_version.get("remote")

        workflow_url = latest_version.get("url")

    raw_description = attributes.get("description")

    return {
        # ---------------------------------------------------------
        # Core canonical metadata
        # ---------------------------------------------------------
        "title": attributes.get("title"),
        "description": clean_description(raw_description),
        "raw_description": (raw_description),
        "version": attributes.get("latest_version"),
        "license": attributes.get("license"),
        "identifiers": extract_identifiers(
            attributes,
            meta,
        ),
        "url": workflow_url,
        "code_repository": (code_repository),
        "keywords": [
            str(tag).strip()
            for tag in as_list(attributes.get("tags"))
            if tag is not None and str(tag).strip()
        ],
        # ---------------------------------------------------------
        # People / organisations
        # ---------------------------------------------------------
        "authors": extract_authors(attributes.get("creators")),
        "organizations": [],
        # ---------------------------------------------------------
        # Types
        # ---------------------------------------------------------
        "types": types,
        # ---------------------------------------------------------
        # Canonical JSON-LD-like term structures
        # ---------------------------------------------------------
        "programming_languages": [],
        "runtime_platforms": (runtime_platforms),
        "software_requirements": [],
        "software_types": (software_types),
        "consumes_data": [],
        "produces_data": [],
        # ---------------------------------------------------------
        # Workflow I/O
        # ---------------------------------------------------------
        "inputs": extract_io_entities(internals.get("inputs")),
        "outputs": extract_io_entities(internals.get("outputs")),
        # ---------------------------------------------------------
        # Dates
        # ---------------------------------------------------------
        "date_created": (attributes.get("created_at")),
        "date_published": None,
        "date_modified": (attributes.get("updated_at")),
        # ---------------------------------------------------------
        # WorkflowHub-specific information
        # ---------------------------------------------------------
        "workflow_class": (workflow_class_term),
        "tools": extract_workflow_tools(attributes.get("tools")),
        "steps": [
            item
            for item in as_list(internals.get("steps"))
            if isinstance(
                item,
                dict,
            )
        ],
        "links": [
            item
            for item in as_list(internals.get("links"))
            if isinstance(
                item,
                dict,
            )
        ],
        # ---------------------------------------------------------
        # WorkflowHub API metadata
        # ---------------------------------------------------------
        "metadata_version": (meta.get("api_version")),
    }
