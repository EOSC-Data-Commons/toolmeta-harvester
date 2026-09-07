from __future__ import annotations

from typing import Any


BIOTOOLS_BASE_URL = "https://bio.tools"


def as_list(
    value: Any,
) -> list[Any]:
    if value is None:
        return []

    if isinstance(value, list):
        return value

    return [value]


def _edam_term(
    value: Any,
) -> dict | None:
    """
    Convert a bio.tools EDAM object:

        {
            "uri": "http://edamontology.org/data_2044",
            "term": "Sequence"
        }

    into a JSON-LD-ish vocabulary term.
    """

    if not isinstance(value, dict):
        return None

    uri = value.get("uri")
    term = value.get("term")

    if not uri and not term:
        return None

    result = {}

    if uri:
        result["@id"] = uri

    if term:
        result["name"] = term

    return result


def _deduplicate_terms(
    values: list[dict],
) -> list[dict]:
    result = []
    seen = set()

    for value in values:
        key = value.get("@id") or value.get("name")

        if key is None:
            result.append(value)
            continue

        if key in seen:
            continue

        seen.add(key)
        result.append(value)

    return result


def _normalize_versions(
    value: Any,
) -> str | None:
    versions = [
        str(version).strip()
        for version in as_list(value)
        if version is not None and str(version).strip()
    ]

    if not versions:
        return None

    # ToolMetadata currently stores a scalar Text version.
    return ", ".join(versions)


def _identifiers(
    tool: dict,
) -> list[str]:
    result = []

    biotools_id = tool.get("biotoolsID")

    curie = tool.get("biotoolsCURIE")

    if curie:
        result.append(str(curie))

    elif biotools_id:
        result.append(f"biotools:{biotools_id}")

    for other in as_list(tool.get("otherID")):
        if not isinstance(other, dict):
            continue

        value = other.get("value")

        if value:
            result.append(str(value))

    return list(dict.fromkeys(result))


def _credit_people(
    tool: dict,
) -> list[dict]:
    """
    Map relevant person credits into schema:author.

    We restrict this to Developer / Contributor roles rather than
    treating every support/contact credit as an author.
    """

    people = []

    accepted_roles = {
        "Developer",
        "Contributor",
    }

    for credit in as_list(tool.get("credit")):
        if not isinstance(
            credit,
            dict,
        ):
            continue

        if credit.get("typeEntity") != "Person":
            continue

        roles = set(as_list(credit.get("typeRole")))

        if roles and not roles.intersection(accepted_roles):
            continue

        person = {
            "@type": "Person",
            "name": credit.get("name"),
        }

        orcid = credit.get("orcidid")

        if orcid:
            person["@id"] = orcid
            person["identifier"] = orcid

        if credit.get("url"):
            person["url"] = credit["url"]

        if credit.get("email"):
            person["email"] = credit["email"]

        people.append(person)

    return people


def _credit_organizations(
    tool: dict,
) -> list[dict]:
    organizations = []

    organization_types = {
        "Project",
        "Division",
        "Institute",
        "Consortium",
        "Funding agency",
    }

    for credit in as_list(tool.get("credit")):
        if not isinstance(
            credit,
            dict,
        ):
            continue

        entity_type = credit.get("typeEntity")

        if entity_type not in organization_types:
            continue

        organization = {
            "@type": "Organization",
            "name": credit.get("name"),
        }

        ror = credit.get("rorid")

        if ror:
            if ror.startswith("http"):
                organization["@id"] = ror
            else:
                organization["@id"] = f"https://ror.org/{ror}"

        elif credit.get("gridid"):
            organization["identifier"] = credit["gridid"]

        if credit.get("url"):
            organization["url"] = credit["url"]

        organizations.append(organization)

    return organizations


def _find_code_repository(
    tool: dict,
) -> str | None:
    """
    Try to identify a source-code repository from bio.tools links.
    """

    for link in as_list(tool.get("link")):
        if not isinstance(link, dict):
            continue

        url = link.get("url")

        if not url:
            continue

        types = {str(value).lower() for value in as_list(link.get("type"))}

        if any("repository" in value or "source code" in value for value in types):
            return str(url)

        lower_url = str(url).lower()

        if any(
            host in lower_url
            for host in (
                "github.com/",
                "gitlab.com/",
                "bitbucket.org/",
            )
        ):
            return str(url)

    return None


def _collect_topics(
    tool: dict,
) -> list[str]:
    values = []

    for topic in as_list(tool.get("topic")):
        if isinstance(topic, dict):
            term = topic.get("term")

            if term:
                values.append(str(term))

    return values


def _collect_operations(
    tool: dict,
) -> list[str]:
    values = []

    for function in as_list(tool.get("function")):
        if not isinstance(
            function,
            dict,
        ):
            continue

        for operation in as_list(function.get("operation")):
            if not isinstance(
                operation,
                dict,
            ):
                continue

            term = operation.get("term")

            if term:
                values.append(str(term))

    return values


def _parameter(
    parameter: dict,
    *,
    parameter_id: str,
) -> dict:
    """
    Convert one bio.tools function input/output parameter into a
    Schema.org-style FormalParameter.
    """

    data = parameter.get("data")

    data_term = _edam_term(data)

    formats = []

    for fmt in as_list(parameter.get("format")):
        if isinstance(fmt, dict):
            if fmt.get("term"):
                formats.append(str(fmt["term"]))
            elif fmt.get("uri"):
                formats.append(str(fmt["uri"]))

    result = {
        "@id": parameter_id,
        "@type": "FormalParameter",
    }

    if data_term:
        result["name"] = data_term.get("name")

        result["additionalType"] = data_term

    if formats:
        result["encodingFormat"] = ", ".join(formats)

    return result


def _extract_function_io(
    tool: dict,
) -> tuple[
    list[dict],
    list[dict],
    list[dict],
    list[dict],
]:
    inputs = []
    outputs = []

    consumes_data = []
    produces_data = []

    for function_index, function in enumerate(as_list(tool.get("function"))):
        if not isinstance(
            function,
            dict,
        ):
            continue

        for input_index, item in enumerate(as_list(function.get("input"))):
            if not isinstance(
                item,
                dict,
            ):
                continue

            parameter = _parameter(
                item,
                parameter_id=(f"#input-{function_index + 1}-{input_index + 1}"),
            )

            inputs.append(parameter)

            data = _edam_term(item.get("data"))

            if data:
                consumes_data.append(data)

        for output_index, item in enumerate(as_list(function.get("output"))):
            if not isinstance(
                item,
                dict,
            ):
                continue

            parameter = _parameter(
                item,
                parameter_id=(f"#output-{function_index + 1}-{output_index + 1}"),
            )

            outputs.append(parameter)

            data = _edam_term(item.get("data"))

            if data:
                produces_data.append(data)

    return (
        inputs,
        outputs,
        _deduplicate_terms(consumes_data),
        _deduplicate_terms(produces_data),
    )


def convert_biotools_to_jsonld(
    tool: dict,
) -> dict:
    """
    Convert a biotoolsSchema JSON record into Schema.org /
    CodeMeta-style JSON-LD suitable for extract_tool_metadata().
    """

    biotools_id = tool.get("biotoolsID") or tool.get("id")

    if not biotools_id:
        raise ValueError("bio.tools record has no biotoolsID")

    (
        inputs,
        outputs,
        consumes_data,
        produces_data,
    ) = _extract_function_io(tool)

    keywords = _collect_topics(tool) + _collect_operations(tool)

    result = {
        "@context": {
            "@vocab": "https://schema.org/",
            "schema": "https://schema.org/",
            "iodata": ("https://w3id.org/software-iodata#"),
            "stype": ("https://w3id.org/software-types#"),
            "edam": ("http://edamontology.org/"),
        },
        "@id": (f"{BIOTOOLS_BASE_URL}/{biotools_id}"),
        "@type": ("SoftwareApplication"),
        "name": tool.get("name"),
        "description": (tool.get("description")),
        "identifier": (_identifiers(tool)),
        "url": (tool.get("homepage") or f"{BIOTOOLS_BASE_URL}/{biotools_id}"),
        "softwareVersion": (_normalize_versions(tool.get("version"))),
        "license": tool.get("license"),
        "programmingLanguage": (as_list(tool.get("language"))),
        # Map bio.tools OS values into the canonical
        # runtimePlatform field used by ScienceToolMeta.
        "runtimePlatform": (as_list(tool.get("operatingSystem"))),
        # CodeMeta extension vocabulary.
        "softwareType": (as_list(tool.get("toolType"))),
        "author": (_credit_people(tool)),
        "producer": (_credit_organizations(tool)),
        "keywords": list(dict.fromkeys(keywords)),
        "input": inputs,
        "output": outputs,
        "iodata:consumesData": (consumes_data),
        "iodata:producesData": (produces_data),
        "dateCreated": (tool.get("additionDate")),
        "dateModified": (tool.get("lastUpdate")),
    }

    code_repository = _find_code_repository(tool)

    if code_repository:
        result["codeRepository"] = code_repository

    # Remove None and empty values.
    return {
        key: value
        for key, value in result.items()
        if value
        not in (
            None,
            "",
            [],
            {},
        )
    }
