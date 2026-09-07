from __future__ import annotations

import json
from typing import Any

CODEMETA_CONTEXT = "https://w3id.org/codemeta/3.1"

def _person(value: Any) -> dict | None:
    if isinstance(value, str):
        return {"@type": "Person", "name": value}
    if not isinstance(value, dict):
        return None
    return {
        k: v for k, v in {
            "@type": "Person",
            "name": value.get("name"),
            "email": value.get("email"),
            "url": value.get("url"),
        }.items() if v
    }

def _repository(value: Any) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return value.get("url")
    return None

def convert_package_json_to_jsonld(content: str | dict) -> dict:
    package = json.loads(content) if isinstance(content, str) else content
    if not isinstance(package, dict):
        raise ValueError("package.json does not contain a JSON object")
    authors = []
    author = _person(package.get("author"))
    if author:
        authors.append(author)
    for value in package.get("contributors", []):
        person = _person(value)
        if person:
            authors.append(person)

    requirements: list[str] = []
    if isinstance(package.get("engines"), dict):
        requirements.extend(
            f"{name} {version}" for name, version in package["engines"].items()
        )
    if isinstance(package.get("dependencies"), dict):
        requirements.extend(
            f"{name} {version}" for name, version in package["dependencies"].items()
        )

    keywords = package.get("keywords")
    if isinstance(keywords, str):
        keywords = [v.strip() for v in keywords.split(",") if v.strip()]

    result = {
        "@context": CODEMETA_CONTEXT,
        "@type": "SoftwareSourceCode",
        "name": package.get("name"),
        "description": package.get("description"),
        "softwareVersion": package.get("version"),
        "license": package.get("license"),
        "url": package.get("homepage"),
        "codeRepository": _repository(package.get("repository")),
        "keywords": keywords,
        "author": authors,
        "softwareRequirements": requirements,
    }
    return {k: v for k, v in result.items() if v not in (None, "", [], {})}
