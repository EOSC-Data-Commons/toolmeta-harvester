from __future__ import annotations

from typing import Any
import yaml

CODEMETA_CONTEXT = "https://w3id.org/codemeta/3.1"

def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]

def _person(author: dict) -> dict:
    given = author.get("given-names") or author.get("given_names")
    family = author.get("family-names") or author.get("family_names")
    name = " ".join(v for v in (given, family) if v).strip()
    result = {"@type": "Person"}
    if name:
        result["name"] = name
    if author.get("orcid"):
        result["@id"] = author["orcid"]
        result["identifier"] = author["orcid"]
    if author.get("email"):
        result["email"] = author["email"]
    if author.get("affiliation"):
        result["affiliation"] = {
            "@type": "Organization",
            "name": author["affiliation"],
        }
    return result

def _identifiers(cff: dict) -> list[str]:
    values: list[str] = []
    doi = cff.get("doi")
    if doi:
        values.append(str(doi) if str(doi).startswith("http") else f"https://doi.org/{doi}")
    for item in _as_list(cff.get("identifiers")):
        if not isinstance(item, dict) or not item.get("value"):
            continue
        value = str(item["value"])
        if item.get("type") == "doi" and not value.startswith("http"):
            value = f"https://doi.org/{value}"
        values.append(value)
    return list(dict.fromkeys(values))

def convert_citation_cff_to_jsonld(content: str | dict) -> dict:
    cff = yaml.safe_load(content) if isinstance(content, str) else content
    if not isinstance(cff, dict):
        raise ValueError("CITATION.cff does not contain a mapping")
    result = {
        "@context": CODEMETA_CONTEXT,
        "@type": "SoftwareSourceCode",
        "name": cff.get("title"),
        "description": cff.get("abstract") or cff.get("message"),
        "softwareVersion": cff.get("version"),
        "license": cff.get("license"),
        "url": cff.get("url"),
        "codeRepository": cff.get("repository-code") or cff.get("repository"),
        "datePublished": cff.get("date-released"),
        "keywords": cff.get("keywords"),
        "identifier": _identifiers(cff),
        "author": [
            _person(a) for a in _as_list(cff.get("authors"))
            if isinstance(a, dict)
        ],
    }
    return {k: v for k, v in result.items() if v not in (None, "", [], {})}
