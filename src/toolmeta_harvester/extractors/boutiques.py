from __future__ import annotations

from typing import Any

from toolmeta_harvester.extractors.description import clean_description


BOUTIQUES_TYPE_MAP = {
    "File": "File",
    "String": "String",
    "Number": "Number",
    "Flag": "Boolean",
}


def extract_author(
    value: str | None,
) -> list[dict[str, Any]]:
    if not value:
        return []

    return [
        {
            "id": None,
            "type": None,
            "name": value.strip(),
            "given_name": None,
            "family_name": None,
            "identifier": None,
            "orcid": None,
            "url": None,
        }
    ]


def extract_container(
    descriptor: dict[str, Any],
) -> list[dict[str, Any]]:
    container = descriptor.get("container-image")

    if not isinstance(container, dict):
        return []

    image = container.get("image")
    container_type = container.get("type")

    if not image:
        return []

    return [
        {
            "id": None,
            "type": [container_type] if container_type else [],
            "name": image,
            "alternate_name": None,
            "identifier": None,
            "url": None,
        }
    ]


def boutiques_type(
    parameter: dict[str, Any],
) -> str | None:
    parameter_type = parameter.get("type")

    if parameter_type == "Number" and parameter.get("integer") is True:
        return "Integer"

    return BOUTIQUES_TYPE_MAP.get(parameter_type)


def extract_input(
    parameter: dict[str, Any],
) -> dict[str, Any]:
    value_type = boutiques_type(parameter)

    optional = parameter.get("optional")

    return {
        "id": parameter.get("id"),
        "name": parameter.get("name"),
        "description": clean_description(parameter.get("description")),
        "type": [value_type] if value_type else [],
        "additional_type": None,
        "encoding_format": None,
        "value_required": (not optional if optional is not None else None),
        "default_value": parameter.get("default-value"),
    }


def extract_output(
    parameter: dict[str, Any],
) -> dict[str, Any]:
    optional = parameter.get("optional")

    return {
        "id": parameter.get("id"),
        "name": parameter.get("name"),
        "description": clean_description(parameter.get("description")),
        "type": ["File"],
        "additional_type": None,
        "encoding_format": None,
        "value_required": (not optional if optional is not None else None),
        "default_value": None,
    }


def extract_inputs(
    descriptor: dict[str, Any],
) -> list[dict[str, Any]]:
    return [
        extract_input(parameter)
        for parameter in descriptor.get("inputs", [])
        if isinstance(parameter, dict)
    ]


def extract_outputs(
    descriptor: dict[str, Any],
) -> list[dict[str, Any]]:
    return [
        extract_output(parameter)
        for parameter in descriptor.get("output-files", [])
        if isinstance(parameter, dict)
    ]


def extract_boutiques_metadata(
    descriptor: dict[str, Any],
) -> dict[str, Any]:
    """
    Convert a Boutiques descriptor into the canonical
    ToolMetadata representation.
    """

    raw_description = descriptor.get("description")

    return {
        "title": descriptor.get("name"),
        "description": clean_description(raw_description),
        "raw_description": raw_description,
        "version": descriptor.get("tool-version"),
        "license": None,
        "identifiers": [],
        "url": None,
        "code_repository": None,
        "keywords": [],
        "authors": extract_author(descriptor.get("author")),
        "organizations": [],
        "types": [
            "SoftwareApplication",
        ],
        "programming_languages": [],
        "runtime_platforms": extract_container(descriptor),
        "software_requirements": [],
        "software_types": [],
        "consumes_data": [],
        "produces_data": [],
        "inputs": extract_inputs(descriptor),
        "outputs": extract_outputs(descriptor),
        "date_created": None,
        "date_published": None,
        "date_modified": None,
    }
