"""Bounded, idempotent generation, optional validation, and embedding operations."""

from __future__ import annotations

import logging
import time
import uuid
from collections import Counter
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session, sessionmaker

from toolmeta_harvester.config import (
    egi_llm_api_key,
    egi_llm_stage_model,
    embedding_api,
    embedding_model,
)
from toolmeta_harvester.db.engine import engine
from toolmeta_harvester.db.models import (
    ToolMetadata,
    ToolMetadataEnrichment,
    ToolMetadataEnrichmentEmbedding,
    ToolMetadataEnrichmentValidation,
)
from toolmeta_harvester.enrichment.input import (
    canonical_json as canonical_json,  # noqa: PLC0414 - public compatibility export
)
from toolmeta_harvester.enrichment.input import (
    generation_input,
    has_source_metadata,
    input_hash,
)
from toolmeta_harvester.enrichment.llm import EgiChatClient
from toolmeta_harvester.enrichment.prompts import generation, validation
from toolmeta_harvester.enrichment.schemas import GenerationResult, ValidationResult
from toolmeta_harvester.tasks.embedding import embed_with_metrics

LOGGER = logging.getLogger(__name__)
SESSION_FACTORY = sessionmaker(bind=engine, expire_on_commit=False)
BATCH_SIZE = 10
MAX_DEFAULT_LIMIT = 100


def _empty_summary(run_id: str | None, selected: int = 0) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "selected_records": selected,
        "generated": 0,
        "skipped_empty_metadata": 0,
        "insufficient_metadata": 0,
        "failed": 0,
        "up_to_date": 0,
        "skipped_inflight": 0,
        "retry_count": 0,
        "llm_requests": 0,
        "processing_seconds": 0.0,
        "average_generation_seconds": 0.0,
        "throughput_per_minute": 0.0,
        "failed_tool_ids": [],
    }


def select_enrichment_batches(
    *,
    tool_ids: list[uuid.UUID] | None,
    limit: int | None,
    full_catalog: bool,
    batch_size: int,
    session_factory: sessionmaker[Session] = SESSION_FACTORY,
) -> list[list[str]]:
    """Select Airflow mapping payloads without performing enrichment work."""
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    if tool_ids:
        if full_catalog:
            raise ValueError("Set either tool_ids or full_catalog, not both")
        ids = list(dict.fromkeys(map(str, tool_ids)))
        return [
            ids[offset : offset + batch_size]
            for offset in range(0, len(ids), batch_size)
        ]
    if full_catalog and limit is not None:
        raise ValueError("Set either full_catalog=true or a limit, not both")
    if not full_catalog:
        if limit is None:
            limit = MAX_DEFAULT_LIMIT
        if limit < 1:
            raise ValueError("limit must be positive")
    batches: list[list[str]] = []
    last_id: uuid.UUID | None = None
    remaining = limit
    with session_factory() as session:
        while True:
            query = (
                select(ToolMetadata.id)
                .order_by(ToolMetadata.id)
                .limit(batch_size if remaining is None else min(batch_size, remaining))
            )
            if last_id is not None:
                query = query.where(ToolMetadata.id > last_id)
            candidate_ids = list(session.scalars(query).all())
            if not candidate_ids:
                break
            batches.append([str(value) for value in candidate_ids])
            last_id = candidate_ids[-1]
            if remaining is not None:
                remaining -= len(candidate_ids)
                if remaining <= 0:
                    break
    return batches


def _current_result_exists(
    session: Session, tool_id: uuid.UUID, digest: str, model: str
) -> bool:
    return (
        session.scalar(
            select(ToolMetadataEnrichment.id)
            .where(
                ToolMetadataEnrichment.tool_id == tool_id,
                ToolMetadataEnrichment.input_hash == digest,
                ToolMetadataEnrichment.requested_model == model,
                ToolMetadataEnrichment.prompt_id == generation.PROMPT_ID,
                ToolMetadataEnrichment.prompt_version == generation.PROMPT_VERSION,
                ToolMetadataEnrichment.status.in_(
                    ["generated", "insufficient_metadata", "skipped_empty_metadata"]
                ),
            )
            .limit(1)
        )
        is not None
    )


def _finish_attempt(
    session_factory: sessionmaker[Session], attempt_id: uuid.UUID, **fields: Any
) -> None:
    with session_factory.begin() as session:
        attempt = session.get(ToolMetadataEnrichment, attempt_id)
        if attempt is not None:
            for key, value in fields.items():
                setattr(attempt, key, value)


def _process_record(
    tool_id: uuid.UUID,
    raw_metadata: Any,
    *,
    run_id: str | None,
    model: str,
    client_factory: Callable[..., Any],
    session_factory: sessionmaker[Session],
) -> dict[str, Any]:
    user_prompt = generation_input(raw_metadata)
    digest = input_hash(user_prompt)
    if not has_source_metadata(raw_metadata):
        status = "skipped_empty_metadata"
        with session_factory.begin() as session:
            if _current_result_exists(session, tool_id, digest, model):
                session.add(
                    ToolMetadataEnrichment(
                        tool_id=tool_id,
                        run_id=run_id,
                        status="up_to_date",
                        requested_model=model,
                        prompt_id=generation.PROMPT_ID,
                        prompt_version=generation.PROMPT_VERSION,
                        input_hash=digest,
                    )
                )
                return {"status": "up_to_date", "requests": 0, "elapsed": 0.0}
            session.add(
                ToolMetadataEnrichment(
                    tool_id=tool_id,
                    run_id=run_id,
                    status=status,
                    requested_model=model,
                    prompt_id=generation.PROMPT_ID,
                    prompt_version=generation.PROMPT_VERSION,
                    input_hash=digest,
                )
            )
        return {"status": status, "requests": 0, "elapsed": 0.0}

    attempt_id = uuid.uuid4()
    with session_factory.begin() as session:
        session.scalar(
            select(ToolMetadata.id).where(ToolMetadata.id == tool_id).with_for_update()
        )
        if _current_result_exists(session, tool_id, digest, model):
            session.add(
                ToolMetadataEnrichment(
                    tool_id=tool_id,
                    run_id=run_id,
                    status="up_to_date",
                    requested_model=model,
                    prompt_id=generation.PROMPT_ID,
                    prompt_version=generation.PROMPT_VERSION,
                    input_hash=digest,
                )
            )
            return {"status": "up_to_date", "requests": 0, "elapsed": 0.0}
        inflight = session.scalar(
            select(ToolMetadataEnrichment)
            .where(
                ToolMetadataEnrichment.tool_id == tool_id,
                ToolMetadataEnrichment.status == "processing",
            )
            .order_by(ToolMetadataEnrichment.generation_timestamp.desc())
            .with_for_update()
            .limit(1)
        )
        if inflight is not None:
            if inflight.generation_timestamp < datetime.now(UTC) - timedelta(
                minutes=30
            ):
                inflight.status = "failed"
                inflight.error_code = "StaleProcessingAttempt"
                inflight.error_message = "The worker stopped before completing this attempt; it was safely made eligible for retry."
            else:
                session.add(
                    ToolMetadataEnrichment(
                        tool_id=tool_id,
                        run_id=run_id,
                        status="skipped_inflight",
                        requested_model=model,
                        prompt_id=generation.PROMPT_ID,
                        prompt_version=generation.PROMPT_VERSION,
                        input_hash=digest,
                    )
                )
                return {"status": "skipped_inflight", "requests": 0, "elapsed": 0.0}
        session.add(
            ToolMetadataEnrichment(
                id=attempt_id,
                tool_id=tool_id,
                run_id=run_id,
                status="processing",
                requested_model=model,
                prompt_id=generation.PROMPT_ID,
                prompt_version=generation.PROMPT_VERSION,
                input_hash=digest,
            )
        )
    started = time.perf_counter()
    client = None
    try:
        client = client_factory(model=model)
        completion = client.complete_json(
            generation.SYSTEM_PROMPT,
            user_prompt,
            validator=GenerationResult.model_validate,
        )
        parsed = GenerationResult.model_validate(completion.data)
        status = parsed.status
        _finish_attempt(
            session_factory,
            attempt_id,
            status=status,
            enriched_description=parsed.enriched_description,
            is_ai_generated=(status == "generated"),
            actual_model=completion.actual_model,
            request_count=completion.request_count,
            elapsed_seconds=completion.elapsed_seconds,
        )
        return {
            "status": status,
            "requests": completion.request_count,
            "elapsed": completion.elapsed_seconds,
            "retries": max(0, completion.request_count - 1),
        }
    except Exception as exc:  # noqa: BLE001 - persist record-level failures and continue the batch
        elapsed = max(
            time.perf_counter() - started,
            float(getattr(client, "last_elapsed_seconds", 0.0)),
        )
        requests = int(getattr(client, "last_request_count", 0))
        error_code = type(exc).__name__
        # Persist only a sanitized error category; provider bodies may contain secrets.
        _finish_attempt(
            session_factory,
            attempt_id,
            status="failed",
            error_code=error_code,
            error_message=f"Generation failed ({error_code}) after {requests} request(s).",
            request_count=requests,
            elapsed_seconds=elapsed,
        )
        LOGGER.warning(
            "Enrichment failed for tool_id=%s error_type=%s", tool_id, error_code
        )
        return {
            "status": "failed",
            "requests": requests,
            "elapsed": elapsed,
            "retries": max(0, requests - 1),
        }


def run_enrichment(
    *,
    tool_ids: list[str],
    run_id: str | None = None,
    client_factory: Callable[..., Any] = EgiChatClient,
    session_factory: sessionmaker[Session] = SESSION_FACTORY,
) -> dict[str, Any]:
    """Process one Airflow-selected batch with a short transaction per record."""
    if not tool_ids or len(tool_ids) > BATCH_SIZE:
        raise ValueError(f"tool_ids must contain between 1 and {BATCH_SIZE} records")
    ids = list(dict.fromkeys(uuid.UUID(value) for value in tool_ids))
    model = egi_llm_stage_model("generation")
    summary = _empty_summary(run_id)
    wall_started = time.perf_counter()
    durations: list[float] = []
    with session_factory() as session:
        records = session.execute(
            select(ToolMetadata.id, ToolMetadata.raw_metadata).where(
                ToolMetadata.id.in_(ids)
            )
        ).all()
    for tool_id, raw_metadata in records:
        summary["selected_records"] += 1
        result = _process_record(
            tool_id,
            raw_metadata,
            run_id=run_id,
            model=model,
            client_factory=client_factory,
            session_factory=session_factory,
        )
        status = result["status"]
        if status in summary and isinstance(summary[status], int):
            summary[status] += 1
        summary["llm_requests"] += result["requests"]
        summary["retry_count"] += result.get("retries", 0)
        if result["elapsed"]:
            durations.append(result["elapsed"])
        if status == "failed":
            summary["failed_tool_ids"].append(str(tool_id))
    elapsed = time.perf_counter() - wall_started
    summary["processing_seconds"] = round(elapsed, 3)
    summary["average_generation_seconds"] = (
        round(sum(durations) / len(durations), 3) if durations else 0.0
    )
    summary["throughput_per_minute"] = (
        round(summary["selected_records"] * 60 / elapsed, 3) if elapsed else 0.0
    )
    return summary


def run_validation(
    *,
    tool_ids: list[str] | None = None,
    enrichment_ids: list[str] | None = None,
    limit: int = 100,
    run_id: str | None = None,
    client_factory: Callable[..., Any] = EgiChatClient,
    session_factory: sessionmaker[Session] = SESSION_FACTORY,
) -> dict[str, Any]:
    """Run optional validation for selected generated results without modifying them."""
    stmt = (
        select(ToolMetadataEnrichment, ToolMetadata.raw_metadata)
        .join(ToolMetadata, ToolMetadata.id == ToolMetadataEnrichment.tool_id)
        .where(ToolMetadataEnrichment.status == "generated")
    )
    if enrichment_ids:
        stmt = stmt.where(
            ToolMetadataEnrichment.id.in_(
                [uuid.UUID(value) for value in enrichment_ids]
            )
        )
    elif tool_ids:
        stmt = stmt.where(
            ToolMetadataEnrichment.tool_id.in_([uuid.UUID(value) for value in tool_ids])
        )
    else:
        stmt = stmt.order_by(ToolMetadataEnrichment.generation_timestamp.desc()).limit(
            min(max(limit, 1), 1000)
        )
    selected = 0
    succeeded = 0
    failed: list[str] = []
    model = egi_llm_stage_model("validation")
    with session_factory() as session:
        rows = session.execute(stmt).all()
    for enrichment, raw_metadata in rows:
        selected += 1
        try:
            completion = client_factory(model=model).complete_json(
                validation.SYSTEM_PROMPT,
                validation.render_user_prompt(
                    raw_metadata, enrichment.enriched_description or ""
                ),
                validator=ValidationResult.model_validate,
            )
            result = ValidationResult.model_validate(completion.data).model_dump(
                mode="json"
            )
            status = "completed"
            error = None
            actual_model = completion.actual_model
        except Exception as exc:  # noqa: BLE001 - keep optional validation failures independent
            status, result, error, actual_model = (
                "failed",
                None,
                type(exc).__name__,
                None,
            )
            failed.append(str(enrichment.tool_id))
        with session_factory.begin() as session:
            session.add(
                ToolMetadataEnrichmentValidation(
                    enrichment_id=enrichment.id,
                    requested_model=model,
                    actual_model=actual_model,
                    prompt_id=validation.PROMPT_ID,
                    prompt_version=validation.PROMPT_VERSION,
                    status=status,
                    result=result,
                    error_message=error,
                )
            )
        succeeded += status == "completed"
    return {
        "run_id": run_id,
        "selected_records": selected,
        "validated": succeeded,
        "failed": len(failed),
        "failed_tool_ids": failed,
    }


def select_pending_embedding_batches(
    *,
    limit: int | None = None,
    full_catalog: bool = True,
    batch_size: int = 10,
    session_factory: sessionmaker[Session] = SESSION_FACTORY,
) -> list[list[str]]:
    """Return bounded Airflow mapping payloads for current results missing vectors."""
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    if full_catalog and limit is not None:
        raise ValueError("Set either full_catalog=true or a limit, not both")
    if not full_catalog:
        limit = 1000 if limit is None else limit
        if limit < 1:
            raise ValueError("limit must be positive")
    model = embedding_model()
    generation_model = egi_llm_stage_model("generation")
    has_embedding = (
        select(ToolMetadataEnrichmentEmbedding.id)
        .where(
            ToolMetadataEnrichmentEmbedding.enrichment_id == ToolMetadataEnrichment.id,
            ToolMetadataEnrichmentEmbedding.embedding_model == model,
        )
        .exists()
    )
    query = (
        select(
            ToolMetadataEnrichment.id,
            ToolMetadataEnrichment.input_hash,
            ToolMetadata.raw_metadata,
        )
        .join(ToolMetadata, ToolMetadata.id == ToolMetadataEnrichment.tool_id)
        .where(
            ToolMetadataEnrichment.status == "generated",
            ToolMetadataEnrichment.enriched_description.is_not(None),
            ToolMetadataEnrichment.is_ai_generated.is_(True),
            ToolMetadataEnrichment.requested_model == generation_model,
            ToolMetadataEnrichment.prompt_id == generation.PROMPT_ID,
            ToolMetadataEnrichment.prompt_version == generation.PROMPT_VERSION,
            ~has_embedding,
        )
        .order_by(
            ToolMetadataEnrichment.generation_timestamp, ToolMetadataEnrichment.id
        )
    )
    batches: list[list[str]] = []
    batch: list[str] = []
    selected = 0
    with session_factory() as session:
        rows = session.execute(query.execution_options(yield_per=250))
        for enrichment_id, expected_hash, raw_metadata in rows:
            if input_hash(generation_input(raw_metadata)) != expected_hash:
                continue
            batch.append(str(enrichment_id))
            selected += 1
            if len(batch) == batch_size:
                batches.append(batch)
                batch = []
            if limit is not None and selected >= limit:
                break
    if batch:
        batches.append(batch)
    return batches


def embed_enrichment_batch(
    *,
    enrichment_ids: list[str],
    session_factory: sessionmaker[Session] = SESSION_FACTORY,
    embedder: Callable[..., Any] = embed_with_metrics,
) -> dict[str, Any]:
    """Embed one Airflow-selected batch, with a vector per attempt and model."""
    if not enrichment_ids or len(enrichment_ids) > BATCH_SIZE:
        raise ValueError(
            f"enrichment_ids must contain between 1 and {BATCH_SIZE} records"
        )
    ids = [uuid.UUID(value) for value in dict.fromkeys(enrichment_ids)]
    model = embedding_model()
    generation_model = egi_llm_stage_model("generation")
    query = (
        select(ToolMetadataEnrichment, ToolMetadata.raw_metadata)
        .join(ToolMetadata, ToolMetadata.id == ToolMetadataEnrichment.tool_id)
        .where(
            ToolMetadataEnrichment.id.in_(ids),
            ToolMetadataEnrichment.status == "generated",
            ToolMetadataEnrichment.is_ai_generated.is_(True),
            ToolMetadataEnrichment.requested_model == generation_model,
            ToolMetadataEnrichment.prompt_id == generation.PROMPT_ID,
            ToolMetadataEnrichment.prompt_version == generation.PROMPT_VERSION,
        )
    )
    with session_factory() as session:
        rows = session.execute(query).all()
    candidates = [
        enrichment
        for enrichment, raw_metadata in rows
        if input_hash(generation_input(raw_metadata)) == enrichment.input_hash
    ]
    api_key = egi_llm_api_key()
    vectors_written = requests_total = 0
    elapsed_total = 0.0
    for offset in range(0, len(candidates), 16):
        batch = candidates[offset : offset + 16]
        result = embedder(
            [row.enriched_description for row in batch],
            api_key=api_key,
            api_url=embedding_api(),
            model=model,
            batch_size=16,
        )
        requests_total += result.request_count
        elapsed_total += result.elapsed_seconds
        with session_factory.begin() as session:
            for enrichment, vector in zip(batch, result.vectors, strict=True):
                statement = (
                    insert(ToolMetadataEnrichmentEmbedding)
                    .values(
                        enrichment_id=enrichment.id,
                        tool_id=enrichment.tool_id,
                        embedding_model=model,
                        actual_model=result.actual_model,
                        text=enrichment.enriched_description,
                        vector=vector,
                        request_count=result.request_count,
                        elapsed_seconds=result.elapsed_seconds,
                    )
                    .on_conflict_do_nothing(
                        constraint="uq_tool_metadata_enrichment_embedding"
                    )
                )
                result_row = cast(CursorResult[Any], session.execute(statement))
                vectors_written += result_row.rowcount or 0
    return {
        "selected_records": len(enrichment_ids),
        "current_candidates": len(candidates),
        "embeddings_written": vectors_written,
        "llm_requests": requests_total,
        "processing_seconds": round(elapsed_total, 3),
    }


def processing_report(
    *,
    run_id: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    session_factory: sessionmaker[Session] = SESSION_FACTORY,
) -> dict[str, Any]:
    """Summarize business outcomes for an Airflow run or time window."""
    stmt = select(ToolMetadataEnrichment)
    if run_id:
        stmt = stmt.where(ToolMetadataEnrichment.run_id == run_id)
    if since:
        stmt = stmt.where(ToolMetadataEnrichment.generation_timestamp >= since)
    if until:
        stmt = stmt.where(ToolMetadataEnrichment.generation_timestamp < until)
    with session_factory() as session:
        rows = list(session.scalars(stmt).all())
        total_tools = session.scalar(select(func.count(ToolMetadata.id))) or 0
        processed_tool_ids = {row.tool_id for row in rows}
    latest_by_tool: dict[uuid.UUID, ToolMetadataEnrichment] = {}
    for row in rows:
        previous = latest_by_tool.get(row.tool_id)
        if previous is None or (row.generation_timestamp, row.id) > (
            previous.generation_timestamp,
            previous.id,
        ):
            latest_by_tool[row.tool_id] = row
    latest_rows = list(latest_by_tool.values())
    counts = Counter(row.status for row in latest_rows)
    durations = [row.elapsed_seconds for row in rows if row.elapsed_seconds is not None]
    requests = sum(row.request_count for row in rows)
    started = min((row.generation_timestamp for row in rows), default=None)
    ended = max((row.generation_timestamp for row in rows), default=None)
    elapsed = sum(durations)
    return {
        "run_id": run_id,
        "period": {
            "since": since.isoformat() if since else None,
            "until": until.isoformat() if until else None,
        },
        "total_selected_records": len(processed_tool_ids),
        "total_attempts": len(rows),
        "successfully_enriched": counts["generated"],
        "skipped_empty_metadata": counts["skipped_empty_metadata"],
        "insufficient_metadata": counts["insufficient_metadata"],
        "failed": counts["failed"],
        "processing": counts["processing"],
        "already_up_to_date": counts["up_to_date"],
        "skipped_inflight": counts["skipped_inflight"],
        "pending_or_unprocessed": max(0, total_tools - len(processed_tool_ids)),
        "retry_count": sum(max(0, row.request_count - 1) for row in rows),
        "llm_requests": requests,
        "processing_seconds": round(elapsed, 3),
        "average_generation_seconds": round(elapsed / len(durations), 3)
        if durations
        else 0.0,
        "throughput_per_minute": round(len(processed_tool_ids) * 60 / elapsed, 3)
        if elapsed
        else 0.0,
        "failed_tool_ids": [
            str(row.tool_id) for row in latest_rows if row.status == "failed"
        ],
        "generation_started_at": started.isoformat() if started else None,
        "generation_ended_at": ended.isoformat() if ended else None,
    }
