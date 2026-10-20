from __future__ import annotations

import json
import logging
import math
import uuid
from collections import Counter
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import String, cast, func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, sessionmaker

from toolmeta_harvester.config import (
    egi_llm_api_key,
    egi_llm_stage_model,
    embedding_api,
)
from toolmeta_harvester.db.engine import engine
from toolmeta_harvester.db.models import (
    ToolEmbedding,
    ToolEnrichment,
    ToolEnrichmentRun,
    ToolMetadata,
)
from toolmeta_harvester.enrichment.input import (
    EnrichmentInput,
    build_enrichment_input,
    enrichment_input_hash,
)
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

LOGGER = logging.getLogger(__name__)
SESSION_FACTORY = sessionmaker(bind=engine, expire_on_commit=False)
SAMPLE_SIZE = 100
STABLE_STAGES = {"extracted", "generated", "validated"}
PROMPT_VERSIONS = {
    "extraction": extraction_v1.PROMPT_VERSION,
    "generation": generation_v1.PROMPT_VERSION,
    "validation": validation_v1.PROMPT_VERSION,
}
RUN_MODEL_FIELDS = {
    "extraction": "requested_extraction_model",
    "generation": "requested_generation_model",
    "validation": "requested_validation_model",
}


def _metadata_payload(value: EnrichmentInput) -> dict[str, Any]:
    return value.model_dump(mode="json", exclude_none=True)


def _extraction_payload(record: ToolEnrichment) -> dict[str, Any]:
    return {
        "input_description": record.input_description or "",
        "output_description": record.output_description or "",
        **(record.semantic_metadata or {}),
    }


def _current_hash(tool: ToolMetadata) -> tuple[EnrichmentInput, str]:
    input_data = build_enrichment_input(tool)
    return input_data, enrichment_input_hash(input_data)


def _complete_json(client: Any, system_prompt: str, user_prompt: str) -> LLMCompletion:
    result = client.complete_json(system_prompt, user_prompt)
    if isinstance(result, LLMCompletion):
        return result
    # Keep small test doubles and downstream custom clients source-compatible.
    model = getattr(client, "model", None)
    return LLMCompletion(
        data=result, requested_model=model or "unknown", actual_model=model
    )


def _set_failure(record: ToolEnrichment, exc: Exception, stage: str) -> None:
    record.status = "failed"
    record.failed_stage = stage
    record.error = f"{type(exc).__name__}: {str(exc)[:1500]}"


def sample_record_ids(session: Session, limit: int = SAMPLE_SIZE) -> list[uuid.UUID]:
    """Deterministically sample every source, then allocate remaining slots by share."""
    if limit < 0:
        raise ValueError("limit must be non-negative")
    source_counts = dict(
        session.execute(
            select(ToolMetadata.metadata_format, func.count()).group_by(
                ToolMetadata.metadata_format
            )
        ).all()
    )
    if limit == 0 or not source_counts:
        return []
    sample_size = min(limit, sum(source_counts.values()))
    formats = sorted(source_counts)
    quotas = {source: 1 for source in formats} if sample_size >= len(formats) else {}
    remaining = sample_size - sum(quotas.values())
    if remaining > 0:
        weights = {
            source: max(source_counts[source] - quotas.get(source, 0), 0)
            for source in formats
        }
        denominator = sum(weights.values())
        exact = {
            source: remaining * weights[source] / denominator for source in formats
        }
        for source in formats:
            quotas[source] = quotas.get(source, 0) + math.floor(exact[source])
        left = sample_size - sum(quotas.values())
        for source in sorted(formats, key=lambda item: (-(exact[item] % 1), item))[
            :left
        ]:
            quotas[source] += 1

    chosen: list[uuid.UUID] = []
    for source in formats:
        count = quotas.get(source, 0)
        if count:
            chosen.extend(
                session.scalars(
                    select(ToolMetadata.id)
                    .where(ToolMetadata.metadata_format == source)
                    .order_by(func.md5(cast(ToolMetadata.id, String)), ToolMetadata.id)
                    .limit(count)
                ).all()
            )
    return chosen


def create_run(
    *,
    limit: int = SAMPLE_SIZE,
    name: str | None = None,
    session_factory: sessionmaker[Session] = SESSION_FACTORY,
) -> uuid.UUID:
    run_id = uuid.uuid4()
    models = {stage: egi_llm_stage_model(stage) for stage in RUN_MODEL_FIELDS}
    with session_factory() as session:
        sample_size = len(sample_record_ids(session, limit))
        run = ToolEnrichmentRun(
            id=run_id,
            name=name or f"enrichment-{datetime.now(UTC):%Y%m%dT%H%M%SZ}",
            requested_extraction_model=models["extraction"],
            requested_generation_model=models["generation"],
            requested_validation_model=models["validation"],
            extraction_prompt_version=extraction_v1.PROMPT_VERSION,
            generation_prompt_version=generation_v1.PROMPT_VERSION,
            validation_prompt_version=validation_v1.PROMPT_VERSION,
            sample_size=sample_size,
        )
        session.add(run)
        session.commit()
    return run_id


def extract_record(tool: ToolMetadata, record: ToolEnrichment, client: Any) -> bool:
    input_data, digest = _current_hash(tool)
    if (
        record.input_hash == digest
        and record.extraction_prompt_version == extraction_v1.PROMPT_VERSION
        and (
            record.status in STABLE_STAGES
            or record.failed_stage in {"generation", "validation"}
        )
    ):
        return False
    if (
        record.input_hash != digest
        or record.extraction_prompt_version != extraction_v1.PROMPT_VERSION
    ):
        record.input_description = None
        record.output_description = None
        record.semantic_metadata = None
        record.enriched_description = None
        record.validation = None
        record.generation_model = None
        record.validation_model = None
        record.generation_prompt_version = None
        record.validation_prompt_version = None
    record.status = "processing"
    record.input_hash = digest
    record.error = None
    record.failed_stage = None
    try:
        completion = _complete_json(
            client,
            extraction_v1.SYSTEM_PROMPT,
            extraction_v1.render_user_prompt(_metadata_payload(input_data)),
        )
        result = SemanticExtraction.model_validate(completion.data)
        record.input_description = result.input_description
        record.output_description = result.output_description
        record.semantic_metadata = {
            "supported_tasks": result.supported_tasks,
            "methods_and_techniques": result.methods_and_techniques,
            "scientific_domains": result.scientific_domains,
        }
        record.extraction_model = completion.actual_model
        record.extraction_prompt_version = extraction_v1.PROMPT_VERSION
        record.status = "extracted"
        record.error = None
        record.failed_stage = None
    except Exception as exc:
        _set_failure(record, exc, "extraction")
        raise
    return True


def generate_record(tool: ToolMetadata, record: ToolEnrichment, client: Any) -> bool:
    input_data, digest = _current_hash(tool)
    if record.input_hash != digest or not record.extraction_prompt_version:
        return False
    if record.status in {"generated", "validated"} and record.generation_prompt_version:
        return False
    if record.status not in {"extracted", "generated", "validated"} and not (
        record.status == "failed"
        and record.failed_stage in {"generation", "validation"}
    ):
        return False
    record.failed_stage = None
    record.validation = None
    try:
        completion = _complete_json(
            client,
            generation_v1.SYSTEM_PROMPT,
            generation_v1.render_user_prompt(
                _metadata_payload(input_data), _extraction_payload(record)
            ),
        )
        result = GeneratedDescription.model_validate(completion.data)
        record.enriched_description = result.enriched_description
        record.generation_model = completion.actual_model
        record.generation_prompt_version = generation_v1.PROMPT_VERSION
        record.status = "generated"
        record.error = None
        record.failed_stage = None
        record.enriched_at = datetime.now(UTC)
    except Exception as exc:
        _set_failure(record, exc, "generation")
        raise
    return True


def validate_record(tool: ToolMetadata, record: ToolEnrichment, client: Any) -> bool:
    input_data, digest = _current_hash(tool)
    if record.input_hash != digest or not record.extraction_prompt_version:
        return False
    if (
        record.status == "validated"
        and record.validation
        and record.validation_prompt_version == validation_v1.PROMPT_VERSION
    ):
        return False
    if not record.generation_prompt_version or not record.enriched_description:
        return False
    if record.status not in {"generated", "validated"} and not (
        record.status == "failed" and record.failed_stage == "validation"
    ):
        return False
    record.failed_stage = None
    try:
        extraction = SemanticExtraction.model_validate(
            {
                "input_description": record.input_description or "",
                "output_description": record.output_description or "",
                **(record.semantic_metadata or {}),
            }
        )
        completion = _complete_json(
            client,
            validation_v1.SYSTEM_PROMPT,
            validation_v1.render_user_prompt(
                _metadata_payload(input_data),
                extraction.model_dump(mode="json"),
                record.enriched_description,
            ),
        )
        result = ValidationResult.model_validate(completion.data)
        record.validation = result.model_dump(mode="json")
        record.validation_model = completion.actual_model
        record.validation_prompt_version = validation_v1.PROMPT_VERSION
        record.status = "validated"
        record.error = None
        record.failed_stage = None
    except Exception as exc:
        _set_failure(record, exc, "validation")
        raise
    return True


STAGE_FUNCTIONS: dict[str, Callable[[ToolMetadata, ToolEnrichment, Any], bool]] = {
    "extraction": extract_record,
    "generation": generate_record,
    "validation": validate_record,
}


def run_stage(
    stage: str,
    *,
    run_id: uuid.UUID | str,
    limit: int | None = None,
    session_factory: sessionmaker[Session] = SESSION_FACTORY,
    client: Any | None = None,
) -> dict[str, Any]:
    if stage not in STAGE_FUNCTIONS:
        raise ValueError(f"Unsupported enrichment stage: {stage}")
    run_id = uuid.UUID(str(run_id))
    with session_factory() as session:
        run = session.get(ToolEnrichmentRun, run_id)
        if run is None:
            raise ValueError(f"Unknown enrichment run: {run_id}")
        ids = sample_record_ids(session, limit or run.sample_size)
        requested_model = getattr(run, RUN_MODEL_FIELDS[stage])
    llm = client or EgiChatClient(model=requested_model)
    stats: Counter[str] = Counter()
    LOGGER.info(
        "enrichment stage selected",
        extra={"stage": stage, "selected": len(ids), "model": requested_model},
    )
    for tool_id in ids:
        with session_factory() as session:
            tool = session.get(ToolMetadata, tool_id)
            if tool is None:
                stats["missing"] += 1
                continue
            record = session.scalar(
                select(ToolEnrichment).where(
                    ToolEnrichment.tool_id == tool_id,
                    ToolEnrichment.run_id == run_id,
                )
            )
            if record is None and stage != "extraction":
                stats["skipped"] += 1
                continue
            if record is None:
                record = ToolEnrichment(tool_id=tool_id, run_id=run_id)
                session.add(record)
                session.flush()
            try:
                processed = STAGE_FUNCTIONS[stage](tool, record, llm)
                session.commit()
                stats["processed" if processed else "skipped"] += 1
            except Exception as exc:  # isolate bad responses per tool
                stats["failed"] += 1
                session.commit()
                LOGGER.warning(
                    "enrichment record failed",
                    extra={"stage": stage, "tool_id": str(tool_id), "reason": str(exc)},
                )
    result = {
        "run_id": str(run_id),
        "stage": stage,
        "selected": len(ids),
        "processed": stats["processed"],
        "skipped": stats["skipped"],
        "failed": stats["failed"],
        "requested_model": requested_model,
        "prompt_version": PROMPT_VERSIONS[stage],
    }
    LOGGER.info("enrichment stage complete", extra=result)
    if stage == "validation":
        with session_factory() as session:
            run = session.get(ToolEnrichmentRun, run_id)
            failures = session.scalar(
                select(func.count())
                .select_from(ToolEnrichment)
                .where(
                    ToolEnrichment.run_id == run_id,
                    ToolEnrichment.status == "failed",
                )
            )
            run.status = "completed_with_errors" if failures else "completed"
            run.finished_at = datetime.now(UTC)
            session.commit()
    return result


def export_review_jsonl(
    path: str | Path,
    *,
    run_id: uuid.UUID | str,
    limit: int = SAMPLE_SIZE,
    session_factory: sessionmaker[Session] = SESSION_FACTORY,
) -> int:
    run_id = uuid.UUID(str(run_id))
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with session_factory() as session, path.open("w", encoding="utf-8") as stream:
        rows = session.execute(
            select(ToolMetadata, ToolEnrichment)
            .join(ToolEnrichment, ToolEnrichment.tool_id == ToolMetadata.id)
            .where(ToolEnrichment.run_id == run_id)
            .order_by(ToolMetadata.metadata_format, ToolMetadata.title)
            .limit(limit)
        )
        count = 0
        for tool, record in rows:
            row = {
                "id": str(tool.id),
                "run_id": str(run_id),
                "source": tool.metadata_format,
                "title": tool.title,
                "description": tool.description,
                "keywords": tool.keywords,
                "inputs": tool.inputs,
                "outputs": tool.outputs,
                "input_description": record.input_description,
                "output_description": record.output_description,
                "semantic_metadata": record.semantic_metadata,
                "enriched_description": record.enriched_description,
                "validation": record.validation,
                "status": record.status,
                "error": record.error,
                "models": {
                    "extraction": record.extraction_model,
                    "generation": record.generation_model,
                    "validation": record.validation_model,
                },
                "prompt_versions": {
                    "extraction": record.extraction_prompt_version,
                    "generation": record.generation_prompt_version,
                    "validation": record.validation_prompt_version,
                },
            }
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
            count += 1
    return count


def run_embedding_stage(
    *,
    run_id: uuid.UUID | str,
    limit: int = SAMPLE_SIZE,
    session_factory: sessionmaker[Session] = SESSION_FACTORY,
) -> int:
    """Embed validated descriptions and link each vector to its run result."""
    from toolmeta_harvester.tasks.embedding import embed

    run_id = uuid.UUID(str(run_id))
    embedding_model = "nomic-embed-text-v2-moe"
    with session_factory() as session:
        records = session.scalars(
            select(ToolEnrichment)
            .where(
                ToolEnrichment.run_id == run_id,
                ToolEnrichment.status == "validated",
                ToolEnrichment.enriched_description.is_not(None),
            )
            .order_by(func.md5(cast(ToolEnrichment.id, String)), ToolEnrichment.id)
            .limit(limit)
        ).all()
        if not records:
            return 0
        vectors = embed(
            [
                record.enriched_description
                for record in records
                if record.enriched_description
            ],
            api_key=egi_llm_api_key(),
            api_url=embedding_api() or "https://llm.ai.egi.eu/embeddings",
            model=embedding_model,
            prefix="search_document: ",
        )
        if len(vectors) != len(records) or any(
            len(vector) != 768 for vector in vectors
        ):
            raise ValueError(
                "Embedding API returned unexpected vector count or dimensions"
            )
        rows = [
            {
                "tool_id": record.tool_id,
                "enrichment_id": record.id,
                "embedding_type": "enriched_description",
                "embedding_model": embedding_model,
                "text": record.enriched_description,
                "vector": vector,
            }
            for record, vector in zip(records, vectors)
        ]
        statement = insert(ToolEmbedding).values(rows)
        session.execute(
            statement.on_conflict_do_update(
                index_elements=[
                    ToolEmbedding.enrichment_id,
                    ToolEmbedding.embedding_type,
                    ToolEmbedding.embedding_model,
                ],
                index_where=text("enrichment_id IS NOT NULL"),
                set_={
                    "text": statement.excluded.text,
                    "vector": statement.excluded.vector,
                    "created_at": func.now(),
                },
            )
        )
        session.commit()
    return len(records)
