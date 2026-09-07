from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class MetadataQualityResult:
    score: float
    passed: bool
    checks: dict[str, bool] = field(default_factory=dict)
    missing: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


DEFAULT_MIN_SCORE = 0.60


def has_value(value: Any) -> bool:
    if value is None:
        return False

    if isinstance(value, str):
        return bool(value.strip())

    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)

    return True


def description_is_meaningful(
    description: str | None,
    min_length: int = 40,
) -> bool:
    """
    Reject empty or trivially short descriptions.
    """

    if not description:
        return False

    return len(description.strip()) >= min_length


def assess_metadata_quality(
    metadata: dict[str, Any],
    min_score: float = DEFAULT_MIN_SCORE,
) -> MetadataQualityResult:
    """
    Perform a rudimentary FAIR/metadata-quality assessment.

    This is intentionally lightweight. It is a harvesting quality gate,
    not a complete FAIR assessment.

    Returns a normalized score between 0 and 1.
    """

    checks: dict[str, bool] = {}
    missing: list[str] = []
    warnings: list[str] = []

    # -------------------------------------------------------------
    # Findability / identity
    # -------------------------------------------------------------

    checks["title"] = has_value(metadata.get("title"))

    checks["identifier"] = has_value(metadata.get("identifiers"))

    checks["url"] = has_value(metadata.get("url"))

    # -------------------------------------------------------------
    # Metadata quality
    # -------------------------------------------------------------

    checks["description"] = description_is_meaningful(metadata.get("description"))

    checks["keywords"] = has_value(metadata.get("keywords"))

    # -------------------------------------------------------------
    # Reusability
    # -------------------------------------------------------------

    checks["license"] = has_value(metadata.get("license"))

    checks["authors"] = has_value(metadata.get("authors"))

    checks["version"] = has_value(metadata.get("version"))

    # -------------------------------------------------------------
    # Scientific software discoverability
    # -------------------------------------------------------------

    checks["types"] = has_value(metadata.get("types"))

    checks["programming_languages"] = has_value(metadata.get("programming_languages"))

    checks["runtime_platforms"] = has_value(metadata.get("runtime_platforms"))

    checks["software_types"] = has_value(metadata.get("software_types"))

    checks["consumes_data"] = has_value(metadata.get("consumes_data"))

    checks["produces_data"] = has_value(metadata.get("produces_data"))

    # -------------------------------------------------------------
    # Weighted score
    # -------------------------------------------------------------

    weights = {
        "title": 1.5,
        "identifier": 1.5,
        "url": 1.0,
        "description": 2.0,
        "keywords": 0.5,
        "license": 1.5,
        "authors": 1.0,
        "version": 0.5,
        "types": 0.5,
        "programming_languages": 0.5,
        "runtime_platforms": 0.25,
        "software_types": 0.25,
        "consumes_data": 0.25,
        "produces_data": 0.25,
    }

    total_weight = sum(weights.values())

    earned = sum(weight for key, weight in weights.items() if checks.get(key, False))

    score = earned / total_weight

    # -------------------------------------------------------------
    # Hard requirements
    # -------------------------------------------------------------

    required = {
        "title",
        "description",
        "identifier",
        "license",
    }

    for field_name in required:
        if not checks[field_name]:
            missing.append(field_name)

    if not checks["authors"]:
        warnings.append("No author/creator metadata")

    if not checks["programming_languages"]:
        warnings.append("No programming language metadata")

    if not checks["consumes_data"] and not checks["produces_data"]:
        warnings.append("No scientific input/output metadata")

    passed = score >= min_score and not missing

    return MetadataQualityResult(
        score=round(score, 3),
        passed=passed,
        checks=checks,
        missing=missing,
        warnings=warnings,
    )
