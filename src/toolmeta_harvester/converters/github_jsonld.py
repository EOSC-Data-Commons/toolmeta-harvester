from __future__ import annotations

import re

CODEMETA_CONTEXT = "https://w3id.org/codemeta/3.1"

def _readme_summary(readme: str | None, max_length: int = 1000) -> str | None:
    if not readme:
        return None
    text = re.sub(r"!\[[^\]]*\]\([^)]+\)", "", readme)
    paragraphs = re.split(r"\n\s*\n", text)
    for paragraph in paragraphs:
        paragraph = re.sub(r"^\s*#+\s*", "", paragraph.strip())
        if not paragraph or paragraph.startswith(("```", "<", "---")):
            continue
        paragraph = " ".join(line.strip() for line in paragraph.splitlines() if line.strip())
        if len(paragraph) >= 40:
            return paragraph[:max_length]
    return None

def convert_github_to_jsonld(
    repository: dict,
    *,
    languages: dict[str, int] | None = None,
    readme: str | None = None,
) -> dict:
    owner = repository.get("owner") or {}
    producer = None
    if owner.get("login"):
        producer = {
            "@type": "Organization" if owner.get("type") == "Organization" else "Person",
            "name": owner.get("login"),
            "url": owner.get("html_url"),
        }

    license_value = None
    if isinstance(repository.get("license"), dict):
        spdx = repository["license"].get("spdx_id")
        if spdx and spdx not in {"NOASSERTION", "OTHER"}:
            license_value = f"https://spdx.org/licenses/{spdx}"

    result = {
        "@context": CODEMETA_CONTEXT,
        "@type": "SoftwareSourceCode",
        "@id": repository.get("html_url"),
        "name": repository.get("name"),
        "description": repository.get("description") or _readme_summary(readme),
        "identifier": [repository.get("full_name")],
        "url": repository.get("homepage") or repository.get("html_url"),
        "codeRepository": repository.get("html_url"),
        "license": license_value,
        "keywords": repository.get("topics"),
        "programmingLanguage": list((languages or {}).keys()),
        "producer": producer,
        "dateCreated": repository.get("created_at"),
        "dateModified": repository.get("pushed_at") or repository.get("updated_at"),
    }
    return {k: v for k, v in result.items() if v not in (None, "", [], {})}

def merge_jsonld(base: dict, override: dict) -> dict:
    result = dict(base)
    for key, value in override.items():
        if value in (None, "", [], {}):
            continue
        if isinstance(value, list) and isinstance(result.get(key), list):
            merged = list(result[key])
            for item in value:
                if item not in merged:
                    merged.append(item)
            result[key] = merged
        else:
            result[key] = value
    return result
