from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

SemanticTerm = Annotated[str, Field(min_length=1, max_length=500)]


def _clean_items(value: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in value:
        normalized = item.strip()
        if normalized and normalized.casefold() not in seen:
            result.append(normalized)
            seen.add(normalized.casefold())
    return result


class SemanticExtraction(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    input_description: str = Field(default="", max_length=2000)
    output_description: str = Field(default="", max_length=2000)
    supported_tasks: list[SemanticTerm] = Field(default_factory=list, max_length=30)
    methods_and_techniques: list[SemanticTerm] = Field(
        default_factory=list, max_length=30
    )
    scientific_domains: list[SemanticTerm] = Field(default_factory=list, max_length=30)

    @field_validator("supported_tasks", "methods_and_techniques", "scientific_domains")
    @classmethod
    def clean_list_items(cls, value: list[str]) -> list[str]:
        return _clean_items(value)


class GeneratedDescription(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    enriched_description: str = Field(min_length=1, max_length=8000)


class ValidationResult(BaseModel):
    """Supplementary LLM review; each score is in the 0–5 range."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    accuracy_score: int = Field(ge=0, le=5)
    completeness_score: int = Field(ge=0, le=5)
    input_quality_score: int = Field(ge=0, le=5)
    output_quality_score: int = Field(ge=0, le=5)
    enriched_description_score: int = Field(ge=0, le=5)
    semantic_usefulness_score: int = Field(ge=0, le=5)
    hallucination_detected: bool
    issues: list[SemanticTerm] = Field(default_factory=list, max_length=30)
    overall_assessment: str = Field(min_length=1, max_length=2000)

    @field_validator("issues")
    @classmethod
    def clean_issues(cls, value: list[str]) -> list[str]:
        return _clean_items(value)
