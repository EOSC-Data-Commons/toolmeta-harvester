from __future__ import annotations

import hashlib
import json
import logging
import re
import time
import uuid
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.dialects.postgresql import insert

from toolmeta_harvester.config import (
    egi_llm_api_key,
    egi_llm_stage_model,
    embedding_api,
    embedding_model,
)
from toolmeta_harvester.db.engine import engine
from toolmeta_harvester.db.models import ToolEmbedding, ToolEnrichment, ToolMetadata
from toolmeta_harvester.enrichment.input import EnrichmentInput, build_enrichment_input
from toolmeta_harvester.enrichment.llm import EgiChatClient, LLMCompletion
from toolmeta_harvester.enrichment.prompts import (
    extraction_v1,
    generation_v1,
    validation_v1,
)
from toolmeta_harvester.enrichment.schemas import (
    GeneratedDescription,
    SemanticExtraction,
    ValidationResult,
)
from toolmeta_harvester.tasks.embedding import embed_with_metrics

LOGGER = logging.getLogger(__name__)
SESSION_FACTORY = sessionmaker(bind=engine, expire_on_commit=False)
SAMPLE_SIZE = 100
PLACEHOLDER_RE = re.compile(
    r"\b(?:TODO|TBD|Lorem ipsum|as an AI language model|insert description here)\b",
    re.IGNORECASE,
)


class EnrichmentBatchError(RuntimeError):
    """Raised after record-level failures have been persisted and summarized."""


@dataclass(frozen=True)
class StageOutput:
    data: dict[str, Any]
    requested_model: str
    actual_model: str | None
    prompt_version: str
    input_hash: str
    request_count: int
    elapsed_seconds: float


def canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def content_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def load_sample_ids(sample_path: str | Path) -> list[uuid.UUID]:
    sample = json.loads(Path(sample_path).read_text(encoding="utf-8"))
    ids = [uuid.UUID(str(value)) for value in sample["tool_ids"]]
    if len(ids) != 100 or len(set(ids)) != 100:
        raise ValueError(
            "The persisted representative sample must contain 100 unique IDs"
        )
    digest = hashlib.sha256("\n".join(map(str, ids)).encode()).hexdigest()
    if sample.get("sample_sha256") != digest:
        raise ValueError("The persisted representative sample failed its SHA-256 check")
    return ids


def _metadata_payload(value: EnrichmentInput) -> dict[str, Any]:
    return value.model_dump(mode="json", exclude_none=True)


def _client_completion(
    client: Any, system_prompt: str, user_prompt: str
) -> LLMCompletion:
    started = time.perf_counter()
    try:
        result = client.complete_json(system_prompt, user_prompt)
    except Exception as exc:
        exc.request_count = int(getattr(client, "last_request_count", 0))
        exc.elapsed_seconds = max(
            float(getattr(client, "last_elapsed_seconds", 0.0)),
            time.perf_counter() - started,
        )
        raise
    if isinstance(result, LLMCompletion):
        return result
    return LLMCompletion(
        data=result,
        requested_model=getattr(client, "model", "unknown"),
        actual_model=getattr(client, "model", None),
        request_count=max(int(getattr(client, "last_request_count", 1)), 1),
        elapsed_seconds=float(getattr(client, "last_elapsed_seconds", 0.0)),
    )


def _request_hash(
    model: str, system_prompt: str, user_prompt: str, *, temperature: float = 0
) -> str:
    return content_hash(
        {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
        }
    )


def extract_semantic_profile(
    metadata: dict[str, Any],
    *,
    requested_model: str | None = None,
    client_factory: Callable[..., Any] = EgiChatClient,
) -> StageOutput:
    model = requested_model or egi_llm_stage_model("extraction")
    user_prompt = extraction_v1.render_user_prompt(metadata)
    digest = _request_hash(model, extraction_v1.SYSTEM_PROMPT, user_prompt)
    completion = _client_completion(
        client_factory(model=model), extraction_v1.SYSTEM_PROMPT, user_prompt
    )
    try:
        data = SemanticExtraction.model_validate(completion.data).model_dump(
            mode="json"
        )
    except Exception as exc:
        exc.request_count = completion.request_count
        exc.elapsed_seconds = completion.elapsed_seconds
        raise
    return StageOutput(
        data=data,
        requested_model=completion.requested_model,
        actual_model=completion.actual_model,
        prompt_version=extraction_v1.PROMPT_VERSION,
        input_hash=digest,
        request_count=completion.request_count,
        elapsed_seconds=completion.elapsed_seconds,
    )


def generate_description(
    metadata: dict[str, Any],
    extraction: dict[str, Any] | None = None,
    *,
    requested_model: str | None = None,
    client_factory: Callable[..., Any] = EgiChatClient,
) -> StageOutput:
    model = requested_model or egi_llm_stage_model("generation")
    user_prompt = generation_v1.render_user_prompt(metadata, extraction)
    digest = _request_hash(model, generation_v1.SYSTEM_PROMPT, user_prompt)
    completion = _client_completion(
        client_factory(model=model), generation_v1.SYSTEM_PROMPT, user_prompt
    )
    try:
        data = GeneratedDescription.model_validate(completion.data).model_dump(
            mode="json"
        )
    except Exception as exc:
        exc.request_count = completion.request_count
        exc.elapsed_seconds = completion.elapsed_seconds
        raise
    return StageOutput(
        data=data,
        requested_model=completion.requested_model,
        actual_model=completion.actual_model,
        prompt_version=generation_v1.PROMPT_VERSION,
        input_hash=digest,
        request_count=completion.request_count,
        elapsed_seconds=completion.elapsed_seconds,
    )


def evaluate_description(
    metadata: dict[str, Any],
    extraction: dict[str, Any] | None,
    description: str,
    *,
    requested_model: str,
    client_factory: Callable[..., Any] = EgiChatClient,
) -> StageOutput:
    user_prompt = validation_v1.render_user_prompt(metadata, extraction, description)
    digest = _request_hash(requested_model, validation_v1.SYSTEM_PROMPT, user_prompt)
    completion = _client_completion(
        client_factory(model=requested_model), validation_v1.SYSTEM_PROMPT, user_prompt
    )
    try:
        data = ValidationResult.model_validate(completion.data).model_dump(mode="json")
    except Exception as exc:
        exc.request_count = completion.request_count
        exc.elapsed_seconds = completion.elapsed_seconds
        raise
    return StageOutput(
        data=data,
        requested_model=completion.requested_model,
        actual_model=completion.actual_model,
        prompt_version=validation_v1.PROMPT_VERSION,
        input_hash=digest,
        request_count=completion.request_count,
        elapsed_seconds=completion.elapsed_seconds,
    )


def deterministic_validation(description: str | None) -> dict[str, Any]:
    value = description or ""
    stripped = value.strip()
    checks = {
        "exists": description is not None,
        "non_empty": bool(stripped),
        "reasonable_length": 30 <= len(stripped) <= 8000,
        "no_placeholder": not bool(PLACEHOLDER_RE.search(stripped)),
        "no_fence_artifacts": not (
            stripped.startswith("```") or stripped.endswith("```")
        ),
    }
    return {
        "passed": all(checks.values()),
        "checks": checks,
        "character_count": len(stripped),
    }


def _set_failure(record: ToolEnrichment, stage: str, error: Exception) -> None:
    record.status = "failed"
    record.failed_stage = stage
    record.error = f"{type(error).__name__}: {str(error)[:1200]}"


def _read_sample_rows(
    sample_ids: list[uuid.UUID], session: Session
) -> list[tuple[uuid.UUID, ToolMetadata]]:
    tools = session.scalars(
        select(ToolMetadata).where(ToolMetadata.id.in_(sample_ids))
    ).all()
    by_id = {tool.id: tool for tool in tools}
    missing = set(sample_ids) - set(by_id)
    if missing:
        raise ValueError(f"Sample references {len(missing)} missing ToolMetadata rows")
    return [(tool_id, by_id[tool_id]) for tool_id in sample_ids]


def run_enrichment_sample(
    *,
    experiment_id: uuid.UUID | str,
    variant: str,
    sample_path: str | Path,
    session_factory: sessionmaker[Session] = SESSION_FACTORY,
    client_factory: Callable[..., Any] = EgiChatClient,
) -> dict[str, Any]:
    """Generate one A/B variant from the persisted sample; Airflow calls this library API."""
    if variant not in {"A", "B"}:
        raise ValueError("variant must be 'A' or 'B'")
    experiment_id = uuid.UUID(str(experiment_id))
    use_extraction = variant == "B"
    tool_ids = load_sample_ids(sample_path)
    requested_generation_model = egi_llm_stage_model("generation")
    requested_extraction_model = (
        egi_llm_stage_model("extraction") if use_extraction else None
    )
    requested_validation_model = egi_llm_stage_model("validation")
    counters: Counter[str] = Counter()
    request_counts: Counter[str] = Counter()
    elapsed: Counter[str] = Counter()
    started = time.perf_counter()

    for tool_id in tool_ids:
        with session_factory() as session:
            tool = session.get(ToolMetadata, tool_id)
            if tool is None:
                counters["missing"] += 1
                continue
            source_input = build_enrichment_input(tool)
            source_hash = content_hash(_metadata_payload(source_input))
            record = session.scalar(
                select(ToolEnrichment).where(
                    ToolEnrichment.tool_id == tool_id,
                    ToolEnrichment.experiment_id == experiment_id,
                    ToolEnrichment.variant == variant,
                )
            )
            if record is None:
                record = ToolEnrichment(
                    tool_id=tool_id,
                    experiment_id=experiment_id,
                    variant=variant,
                    extraction_used=use_extraction,
                    requested_extraction_model=requested_extraction_model,
                    requested_model=requested_generation_model,
                    requested_validation_model=requested_validation_model,
                    extraction_prompt_version=(
                        extraction_v1.PROMPT_VERSION if use_extraction else None
                    ),
                    prompt_version=generation_v1.PROMPT_VERSION,
                )
                session.add(record)
                session.flush()
            elif record.extraction_used != use_extraction:
                raise ValueError(f"Variant mismatch for enrichment row {record.id}")
            if record.status == "completed" and record.source_hash == source_hash:
                counters["skipped"] += 1
                continue
            if record.source_hash and record.source_hash != source_hash:
                raise ValueError(
                    f"Source metadata changed during experiment for tool {tool_id}; "
                    "create a new experiment ID to preserve reproducibility"
                )
            record.source_hash = source_hash
            record.status = "processing"
            record.error = None
            record.failed_stage = None
            session.commit()

            metadata = _metadata_payload(source_input)
            extraction_profile: dict[str, Any] | None = None
            try:
                if use_extraction:
                    extraction_user = extraction_v1.render_user_prompt(metadata)
                    extraction_hash = _request_hash(
                        requested_extraction_model,
                        extraction_v1.SYSTEM_PROMPT,
                        extraction_user,
                    )
                    if (
                        record.extraction_result
                        and record.extraction_input_hash == extraction_hash
                        and record.extraction_prompt_version
                        == extraction_v1.PROMPT_VERSION
                    ):
                        extraction_profile = record.extraction_result
                    else:
                        stage_started = time.perf_counter()
                        try:
                            stage = extract_semantic_profile(
                                metadata,
                                requested_model=requested_extraction_model,
                                client_factory=client_factory,
                            )
                        except Exception as exc:
                            record.extraction_request_count += int(
                                getattr(exc, "request_count", 0)
                            )
                            record.extraction_elapsed_seconds = (
                                record.extraction_elapsed_seconds or 0.0
                            ) + float(
                                getattr(
                                    exc,
                                    "elapsed_seconds",
                                    time.perf_counter() - stage_started,
                                )
                            )
                            raise
                        duration = max(
                            stage.elapsed_seconds, time.perf_counter() - stage_started
                        )
                        request_counts["extraction"] += stage.request_count
                        elapsed["extraction"] += duration
                        record.extraction_request_count += stage.request_count
                        record.extraction_elapsed_seconds = (
                            record.extraction_elapsed_seconds or 0.0
                        ) + duration
                        extraction_profile = stage.data
                        record.extraction_validation = {
                            "passed": True,
                            "schema": SemanticExtraction.__name__,
                        }
                        record.extraction_result = extraction_profile
                        record.requested_extraction_model = stage.requested_model
                        record.extraction_model = stage.actual_model
                        record.extraction_input_hash = stage.input_hash
                        record.extraction_prompt_version = stage.prompt_version
                        session.commit()
                generation_user = generation_v1.render_user_prompt(
                    metadata, extraction_profile
                )
                generation_hash = _request_hash(
                    requested_generation_model,
                    generation_v1.SYSTEM_PROMPT,
                    generation_user,
                )
                if (
                    record.status == "completed"
                    and record.input_hash == generation_hash
                ):
                    counters["skipped"] += 1
                    continue
                stage_started = time.perf_counter()
                try:
                    stage = generate_description(
                        metadata,
                        extraction_profile,
                        requested_model=requested_generation_model,
                        client_factory=client_factory,
                    )
                except Exception as exc:
                    record.generation_request_count += int(
                        getattr(exc, "request_count", 0)
                    )
                    record.generation_elapsed_seconds = (
                        record.generation_elapsed_seconds or 0.0
                    ) + float(
                        getattr(
                            exc,
                            "elapsed_seconds",
                            time.perf_counter() - stage_started,
                        )
                    )
                    raise
                duration = max(
                    stage.elapsed_seconds, time.perf_counter() - stage_started
                )
                request_counts["generation"] += stage.request_count
                elapsed["generation"] += duration
                record.generation_request_count += stage.request_count
                record.generation_elapsed_seconds = (
                    record.generation_elapsed_seconds or 0.0
                ) + duration
                record.enriched_description = stage.data["enriched_description"]
                record.input_hash = stage.input_hash
                record.requested_model = stage.requested_model
                record.model = stage.actual_model
                record.prompt_version = stage.prompt_version
                record.deterministic_validation = deterministic_validation(
                    stage.data["enriched_description"]
                )
                record.status = "completed"
                record.error = None
                record.failed_stage = None
                session.commit()
                counters["processed"] += 1
            except Exception as exc:
                error_request_count = int(getattr(exc, "request_count", 0))
                error_elapsed = float(getattr(exc, "elapsed_seconds", 0.0))
                failed_stage = (
                    "extraction"
                    if use_extraction and not record.extraction_result
                    else "generation"
                )
                if failed_stage == "extraction":
                    record.extraction_request_count += error_request_count
                    record.extraction_elapsed_seconds = (
                        record.extraction_elapsed_seconds or 0.0
                    ) + error_elapsed
                else:
                    record.generation_request_count += error_request_count
                    record.generation_elapsed_seconds = (
                        record.generation_elapsed_seconds or 0.0
                    ) + error_elapsed
                _set_failure(record, failed_stage, exc)
                session.commit()
                counters["failed"] += 1
                LOGGER.exception(
                    "Tool enrichment failed",
                    extra={
                        "experiment_id": str(experiment_id),
                        "variant": variant,
                        "tool_id": str(tool_id),
                    },
                )

    result = {
        "experiment_id": str(experiment_id),
        "variant": variant,
        "extraction_used": use_extraction,
        "sample_size": len(tool_ids),
        "processed": counters["processed"],
        "skipped": counters["skipped"],
        "failed": counters["failed"],
        "missing": counters["missing"],
        "requested_extraction_model": requested_extraction_model,
        "requested_model": requested_generation_model,
        "requested_validation_model": requested_validation_model,
        "extraction_prompt_version": extraction_v1.PROMPT_VERSION
        if use_extraction
        else None,
        "prompt_version": generation_v1.PROMPT_VERSION,
        "request_counts": dict(request_counts),
        "elapsed_seconds_by_stage": dict(elapsed),
        "total_elapsed_seconds": time.perf_counter() - started,
    }
    LOGGER.info("Enrichment sample finished: %s", canonical_json(result))
    if result["failed"] or result["missing"]:
        raise EnrichmentBatchError(canonical_json(result))
    return result


def run_validation_sample(
    *,
    experiment_id: uuid.UUID | str,
    variant: str,
    sample_path: str | Path,
    session_factory: sessionmaker[Session] = SESSION_FACTORY,
    client_factory: Callable[..., Any] = EgiChatClient,
) -> dict[str, Any]:
    """Run deterministic and LLM validation independently of embedding."""
    if variant not in {"A", "B"}:
        raise ValueError("variant must be 'A' or 'B'")
    experiment_id = uuid.UUID(str(experiment_id))
    tool_ids = load_sample_ids(sample_path)
    counters: Counter[str] = Counter()
    request_count = 0
    elapsed_total = 0.0
    requested_model = egi_llm_stage_model("validation")
    started = time.perf_counter()
    for tool_id in tool_ids:
        with session_factory() as session:
            record = session.scalar(
                select(ToolEnrichment).where(
                    ToolEnrichment.tool_id == tool_id,
                    ToolEnrichment.experiment_id == experiment_id,
                    ToolEnrichment.variant == variant,
                )
            )
            if (
                record is None
                or record.status != "completed"
                or not record.enriched_description
            ):
                counters["skipped"] += 1
                continue
            if (
                record.validation_status == "completed"
                and record.validation_prompt_version == validation_v1.PROMPT_VERSION
            ):
                counters["skipped"] += 1
                continue
            tool = session.get(ToolMetadata, tool_id)
            if tool is None:
                counters["missing"] += 1
                continue
            metadata = _metadata_payload(build_enrichment_input(tool))
            extraction = record.extraction_result if record.extraction_used else None
            deterministic = deterministic_validation(record.enriched_description)
            record.deterministic_validation = deterministic
            stage_started = time.perf_counter()
            try:
                stage = evaluate_description(
                    metadata,
                    extraction,
                    record.enriched_description,
                    requested_model=record.requested_validation_model
                    or requested_model,
                    client_factory=client_factory,
                )
                duration = max(
                    stage.elapsed_seconds, time.perf_counter() - stage_started
                )
                record.validation = stage.data
                record.validation_model = stage.actual_model
                record.validation_prompt_version = stage.prompt_version
                record.requested_validation_model = stage.requested_model
                record.validation_status = "completed"
                record.validation_request_count += stage.request_count
                record.validation_elapsed_seconds = (
                    record.validation_elapsed_seconds or 0.0
                ) + duration
                session.commit()
                counters["processed"] += 1
                request_count += stage.request_count
                elapsed_total += duration
            except Exception as exc:
                record.validation_request_count += int(getattr(exc, "request_count", 0))
                record.validation_elapsed_seconds = (
                    record.validation_elapsed_seconds or 0.0
                ) + float(
                    getattr(
                        exc,
                        "elapsed_seconds",
                        time.perf_counter() - stage_started,
                    )
                )
                record.validation_status = "failed"
                record.validation = None
                record.validation_prompt_version = validation_v1.PROMPT_VERSION
                record.error = f"{type(exc).__name__}: {str(exc)[:1200]}"
                session.commit()
                counters["failed"] += 1
                LOGGER.exception(
                    "Tool validation failed",
                    extra={
                        "experiment_id": str(experiment_id),
                        "variant": variant,
                        "tool_id": str(tool_id),
                    },
                )
    summary = {
        "experiment_id": str(experiment_id),
        "variant": variant,
        "sample_size": len(tool_ids),
        "processed": counters["processed"],
        "skipped": counters["skipped"],
        "failed": counters["failed"],
        "missing": counters["missing"],
        "requested_model": requested_model,
        "prompt_version": validation_v1.PROMPT_VERSION,
        "request_count": request_count,
        "elapsed_seconds": elapsed_total,
        "total_elapsed_seconds": time.perf_counter() - started,
    }
    LOGGER.info("Validation sample finished: %s", canonical_json(summary))
    if summary["failed"] or summary["missing"]:
        raise EnrichmentBatchError(canonical_json(summary))
    return summary


def embed_pending_enrichments(
    *,
    session_factory: sessionmaker[Session] = SESSION_FACTORY,
    batch_size: int = 16,
) -> dict[str, Any]:
    """Embed completed enrichments; validation state is deliberately not a prerequisite."""
    with session_factory() as session:
        records = session.scalars(
            select(ToolEnrichment)
            .where(
                ToolEnrichment.status == "completed",
                ToolEnrichment.enriched_description.is_not(None),
                ~select(ToolEmbedding.id)
                .where(ToolEmbedding.enrichment_id == ToolEnrichment.id)
                .exists(),
            )
            .order_by(ToolEnrichment.created_at, ToolEnrichment.id)
        ).all()
        if not records:
            return {"processed": 0, "request_count": 0, "elapsed_seconds": 0.0}
        texts = [record.enriched_description or "" for record in records]
        result = embed_with_metrics(
            texts,
            api_key=egi_llm_api_key(),
            api_url=embedding_api(),
            model=embedding_model(),
            batch_size=batch_size,
        )
        if len(result.vectors) != len(records):
            raise ValueError(
                f"Embedding API returned {len(result.vectors)} vectors for {len(records)} records"
            )
        if any(len(vector) != 768 for vector in result.vectors):
            raise ValueError(
                "Embedding API returned a vector with a dimension other than 768"
            )
        api_by_row: dict[int, dict[str, Any]] = {}
        for batch in result.batches:
            batch_id = uuid.uuid4()
            for index in range(int(batch["start"]), int(batch["stop"])):
                api_by_row[index] = {**batch, "batch_id": batch_id}
        rows = []
        for index, (record, vector) in enumerate(
            zip(records, result.vectors, strict=True)
        ):
            batch = api_by_row[index]
            rows.append(
                {
                    "tool_id": record.tool_id,
                    "enrichment_id": record.id,
                    "embedding_type": "enriched_description",
                    "embedding_model": result.requested_model,
                    "actual_model": result.actual_model,
                    "embedding_batch_id": batch["batch_id"],
                    "request_count": int(batch["request_count"]),
                    "elapsed_seconds": float(batch["elapsed_seconds"]),
                    "text": record.enriched_description,
                    "vector": vector,
                }
            )
        statement = insert(ToolEmbedding).values(rows)
        session.execute(
            statement.on_conflict_do_update(
                index_elements=[
                    ToolEmbedding.enrichment_id,
                    ToolEmbedding.embedding_type,
                    ToolEmbedding.embedding_model,
                ],
                index_where=(ToolEmbedding.enrichment_id.is_not(None)),
                set_={
                    "actual_model": statement.excluded.actual_model,
                    "embedding_batch_id": statement.excluded.embedding_batch_id,
                    "request_count": statement.excluded.request_count,
                    "elapsed_seconds": statement.excluded.elapsed_seconds,
                    "text": statement.excluded.text,
                    "vector": statement.excluded.vector,
                    "created_at": func.now(),
                },
            )
        )
        session.commit()
    summary = {
        "processed": len(records),
        "requested_model": result.requested_model,
        "actual_model": result.actual_model,
        "dimensions": len(result.vectors[0]) if result.vectors else 0,
        "request_count": result.request_count,
        "elapsed_seconds": result.elapsed_seconds,
        "batch_count": len(result.batches),
    }
    LOGGER.info("Embedding stage finished: %s", canonical_json(summary))
    return summary
