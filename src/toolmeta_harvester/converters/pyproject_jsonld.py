from __future__ import annotations

import tomllib
from typing import Any

CODEMETA_CONTEXT = "https://w3id.org/codemeta/3.1"

def _person(value: dict) -> dict:
    return {
        k: v for k, v in {
            "@type": "Person",
            "name": value.get("name"),
            "email": value.get("email"),
        }.items() if v
    }

def _license(project: dict) -> str | None:
    value = project.get("license")
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return value.get("text") or value.get("file")
    return None

def _url(urls: dict[str, Any], *names: str) -> str | None:
    normalized = {str(k).lower(): v for k, v in urls.items()}
    for name in names:
        if normalized.get(name.lower()):
            return str(normalized[name.lower()])
    return None

def convert_pyproject_to_jsonld(content: str | bytes | dict) -> dict:
    if isinstance(content, dict):
        document = content
    else:
        if isinstance(content, bytes):
            content = content.decode("utf-8")
        document = tomllib.loads(content)
    project = document.get("project")
    if not isinstance(project, dict):
        raise ValueError("pyproject.toml has no [project] table")
    urls = project.get("urls") or {}
    if not isinstance(urls, dict):
        urls = {}
    requirements: list[str] = []
    if project.get("requires-python"):
        requirements.append(f"Python {project['requires-python']}")
    requirements.extend(str(v) for v in project.get("dependencies", []))
    result = {
        "@context": CODEMETA_CONTEXT,
        "@type": "SoftwareSourceCode",
        "name": project.get("name"),
        "description": project.get("description"),
        "softwareVersion": project.get("version"),
        "license": _license(project),
        "keywords": project.get("keywords"),
        "url": _url(urls, "homepage", "home"),
        "codeRepository": _url(urls, "repository", "source", "source code", "code"),
        "programmingLanguage": ["Python"],
        "softwareRequirements": requirements,
        "author": [
            _person(a) for a in project.get("authors", [])
            if isinstance(a, dict)
        ],
    }
    return {k: v for k, v in result.items() if v not in (None, "", [], {})}
