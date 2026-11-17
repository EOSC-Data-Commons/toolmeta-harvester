from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class GenerationResult(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    status: Literal["generated", "insufficient_metadata"]
    enriched_description: (
        Annotated[str, Field(min_length=1, max_length=8000)] | None
    ) = None

    @model_validator(mode="after")
    def ensure_description_matches_status(self) -> GenerationResult:
        if self.status == "generated" and not self.enriched_description:
            raise ValueError("generated status requires a non-empty description")
        if (
            self.status == "insufficient_metadata"
            and self.enriched_description is not None
        ):
            raise ValueError("insufficient_metadata must not include a description")
        return self


class ValidationResult(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    accuracy_score: int = Field(ge=0, le=5)
    completeness_score: int = Field(ge=0, le=5)
    hallucination_detected: bool
    issues: list[str] = Field(default_factory=list, max_length=30)
    overall_assessment: str = Field(min_length=1, max_length=2000)
