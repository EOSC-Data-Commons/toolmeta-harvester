from __future__ import annotations


def convert_gitlab_to_jsonld(
    project: dict,
    *,
    languages: dict | None = None,
    readme: str | None = None,
) -> dict:
    """
    Convert GitLab project metadata into a schema.org / CodeMeta-like
    JSON-LD representation.
    """

    languages = languages or {}

    result = {
        "@context": "https://schema.org",
        "@type": "SoftwareSourceCode",
        "@id": project.get("web_url"),
        "name": project.get("name"),
        "description": project.get("description"),
        "codeRepository": project.get("web_url"),
        "url": project.get("web_url"),
        "identifier": project.get("path_with_namespace"),
    }

    topics = project.get("topics") or project.get("tag_list") or []

    if topics:
        result["keywords"] = topics

    if languages:
        result["programmingLanguage"] = [
            {
                "@type": "ComputerLanguage",
                "name": language,
            }
            for language in languages
        ]

    namespace = project.get("namespace")

    if namespace:
        result["publisher"] = {
            "@type": "Organization",
            "name": namespace.get("name"),
            "url": namespace.get("web_url"),
        }

    if project.get("created_at"):
        result["dateCreated"] = project["created_at"]

    if project.get("last_activity_at"):
        result["dateModified"] = project["last_activity_at"]

    if readme:
        result["abstract"] = readme

    return {key: value for key, value in result.items() if value is not None}


def merge_jsonld(
    base: dict,
    additional: dict,
) -> dict:
    """
    Merge generated metadata with repository metadata.

    Values in additional metadata take precedence.
    """

    merged = dict(base)

    for key, value in additional.items():
        if value is None:
            continue

        if key in {"@context", "@type"}:
            continue

        merged[key] = value

    return merged
