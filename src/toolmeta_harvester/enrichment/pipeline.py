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

from sqlalchemy import String, cast, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, sessionmaker

from toolmeta_harvester.config import egi_llm_api_key, embedding_api
from toolmeta_harvester.db.engine import engine
from toolmeta_harvester.db.models import ToolEmbedding, ToolMetadata
from toolmeta_harvester.enrichment.input import (
    EnrichmentInput,
    build_enrichment_input,
    enrichment_input_hash,
)
from toolmeta_harvester.enrichment.llm import EgiChatClient
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


def _metadata_payload(value: EnrichmentInput) -> dict[str, Any]:
    return value.model_dump(mode="json", exclude_none=True)


def _extraction_payload(record: ToolMetadata) -> dict[str, Any]:
    return {
        "input_description": record.input_description or "",
        "output_description": record.output_description or "",
        **(record.semantic_metadata or {}),
    }


def _set_failure(record: ToolMetadata, exc: Exception, stage: str) -> None:
    record.enrichment_status = "failed"
    record.enrichment_failed_stage = stage
    record.enrichment_error = f"{type(exc).__name__}: {str(exc)[:1500]}"


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
    total = sum(source_counts.values())
    sample_size = min(limit, total)
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
        if not count:
            continue
        chosen.extend(
            session.scalars(
                select(ToolMetadata.id)
                .where(ToolMetadata.metadata_format == source)
                .order_by(func.md5(cast(ToolMetadata.id, String)), ToolMetadata.id)
                .limit(count)
            ).all()
        )
    return chosen


def _current_hash(record: ToolMetadata) -> tuple[EnrichmentInput, str]:
    input_data = build_enrichment_input(record)
    return input_data, enrichment_input_hash(input_data)


def _record_has_version(record: ToolMetadata, version: str) -> bool:
    return version in (record.enrichment_version or "").split("+")


def extract_record(record: ToolMetadata, client: EgiChatClient) -> bool:
    input_data, digest = _current_hash(record)
    same_input = record.enrichment_input_hash == digest
    same_prompt = _record_has_version(record, extraction_v1.PROMPT_VERSION)
    if (
        same_input
        and same_prompt
        and (
            record.enrichment_status in STABLE_STAGES
            or record.enrichment_failed_stage in {"generation", "validation"}
        )
    ):
        return False
    if not same_input or not same_prompt:
        record.input_description = None
        record.output_description = None
        record.semantic_metadata = None
        record.enriched_description = None
        record.enrichment_validation = None
    record.enrichment_status = "processing"
    record.enrichment_input_hash = digest
    record.enrichment_error = None
    record.enrichment_failed_stage = None
    try:
        result = SemanticExtraction.model_validate(
            client.complete_json(
                extraction_v1.SYSTEM_PROMPT,
                extraction_v1.render_user_prompt(_metadata_payload(input_data)),
            )
        )
        record.input_description = result.input_description
        record.output_description = result.output_description
        record.semantic_metadata = {
            "supported_tasks": result.supported_tasks,
            "methods_and_techniques": result.methods_and_techniques,
            "scientific_domains": result.scientific_domains,
        }
        record.enrichment_status = "extracted"
        record.enrichment_version = extraction_v1.PROMPT_VERSION
        record.enrichment_error = None
        record.enrichment_failed_stage = None
    except Exception as exc:
        _set_failure(record, exc, "extraction")
        raise
    return True


def generate_record(record: ToolMetadata, client: EgiChatClient) -> bool:
    input_data, digest = _current_hash(record)
    if record.enrichment_input_hash != digest:
        record.enrichment_status = "pending"
        return False
    has_current_extraction = _record_has_version(record, extraction_v1.PROMPT_VERSION)
    has_current_generation = _record_has_version(record, generation_v1.PROMPT_VERSION)
    if not has_current_extraction:
        return False
    if (
        record.enrichment_status in {"generated", "validated"}
        and has_current_generation
        and record.enriched_description
    ) or (
        record.enrichment_status == "failed"
        and record.enrichment_failed_stage == "validation"
        and has_current_generation
    ):
        return False
    if record.enrichment_status not in {"extracted", "generated", "validated"} and not (
        record.enrichment_status == "failed"
        and record.enrichment_failed_stage in {"generation", "validation"}
    ):
        return False
    record.enrichment_failed_stage = None
    record.enrichment_validation = None
    try:
        result = GeneratedDescription.model_validate(
            client.complete_json(
                generation_v1.SYSTEM_PROMPT,
                generation_v1.render_user_prompt(
                    _metadata_payload(input_data), _extraction_payload(record)
                ),
            )
        )
        record.enriched_description = result.enriched_description
        record.enrichment_status = "generated"
        record.enrichment_version = (
            f"{extraction_v1.PROMPT_VERSION}+{generation_v1.PROMPT_VERSION}"
        )
        record.enrichment_error = None
        record.enrichment_failed_stage = None
        record.enriched_at = datetime.now(UTC)
    except Exception as exc:
        _set_failure(record, exc, "generation")
        raise
    return True


def validate_record(record: ToolMetadata, client: EgiChatClient) -> bool:
    input_data, digest = _current_hash(record)
    if record.enrichment_input_hash != digest:
        record.enrichment_status = "pending"
        return False
    if (
        record.enrichment_status == "validated"
        and record.enrichment_validation
        and _record_has_version(record, extraction_v1.PROMPT_VERSION)
        and _record_has_version(record, generation_v1.PROMPT_VERSION)
        and _record_has_version(record, validation_v1.PROMPT_VERSION)
    ):
        return False
    if not _record_has_version(record, extraction_v1.PROMPT_VERSION):
        return False
    if not _record_has_version(record, generation_v1.PROMPT_VERSION):
        return False
    if record.enrichment_status not in {"generated", "validated"} and not (
        record.enrichment_status == "failed"
        and record.enrichment_failed_stage == "validation"
    ):
        return False
    if not record.enriched_description:
        return False
    record.enrichment_failed_stage = None
    try:
        # Deterministic checks protect persistence even if an LLM response is malformed.
        extraction = SemanticExtraction.model_validate(
            {
                "input_description": record.input_description or "",
                "output_description": record.output_description or "",
                **(record.semantic_metadata or {}),
            }
        )
        if not record.enriched_description.strip():
            raise ValueError("enriched_description is empty")
        result = ValidationResult.model_validate(
            client.complete_json(
                validation_v1.SYSTEM_PROMPT,
                validation_v1.render_user_prompt(
                    _metadata_payload(input_data),
                    extraction.model_dump(mode="json"),
                    record.enriched_description,
                ),
            )
        )
        record.enrichment_validation = result.model_dump(mode="json")
        record.enrichment_status = "validated"
        record.enrichment_version = (
            f"{extraction_v1.PROMPT_VERSION}+{generation_v1.PROMPT_VERSION}"
            f"+{validation_v1.PROMPT_VERSION}"
        )
        record.enrichment_error = None
    except Exception as exc:
        _set_failure(record, exc, "validation")
        raise
    return True


STAGE_FUNCTIONS: dict[str, Callable[[ToolMetadata, EgiChatClient], bool]] = {
    "extraction": extract_record,
    "generation": generate_record,
    "validation": validate_record,
}


def run_stage(
    stage: str,
    *,
    limit: int = SAMPLE_SIZE,
    session_factory: sessionmaker[Session] = SESSION_FACTORY,
    client: EgiChatClient | None = None,
) -> dict[str, Any]:
    if stage not in STAGE_FUNCTIONS:
        raise ValueError(f"Unsupported enrichment stage: {stage}")
    llm = client or EgiChatClient()
    with session_factory() as session:
        ids = sample_record_ids(session, limit)
    stats: Counter[str] = Counter()
    LOGGER.info(
        "enrichment stage selected",
        extra={"stage": stage, "selected": len(ids), "model": llm.model},
    )
    for record_id in ids:
        with session_factory() as session:
            record = session.get(ToolMetadata, record_id)
            if record is None:
                stats["missing"] += 1
                continue
            try:
                processed = STAGE_FUNCTIONS[stage](record, llm)
                session.commit()
                stats["processed" if processed else "skipped"] += 1
            except Exception as exc:  # noqa: BLE001 - isolate record failures in a batch
                stats["failed"] += 1
                session.commit()
                LOGGER.warning(
                    "enrichment record failed",
                    extra={
                        "stage": stage,
                        "record_id": str(record_id),
                        "reason": str(exc),
                    },
                )
    result = {
        "stage": stage,
        "selected": len(ids),
        "processed": stats["processed"],
        "skipped": stats["skipped"],
        "failed": stats["failed"],
        "model": llm.model,
        "prompt_version": {
            "extraction": extraction_v1.PROMPT_VERSION,
            "generation": generation_v1.PROMPT_VERSION,
            "validation": validation_v1.PROMPT_VERSION,
        }[stage],
    }
    LOGGER.info("enrichment stage complete", extra=result)
    return result


def export_review_jsonl(
    path: str | Path,
    *,
    limit: int = SAMPLE_SIZE,
    session_factory: sessionmaker[Session] = SESSION_FACTORY,
) -> int:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with session_factory() as session, path.open("w", encoding="utf-8") as stream:
        ids = sample_record_ids(session, limit)
        for record_id in ids:
            record = session.get(ToolMetadata, record_id)
            if record is None:
                continue
            row = {
                "id": str(record.id),
                "source": record.metadata_format,
                "title": record.title,
                "description": record.description,
                "keywords": record.keywords,
                "inputs": record.inputs,
                "outputs": record.outputs,
                "input_description": record.input_description,
                "output_description": record.output_description,
                "semantic_metadata": record.semantic_metadata,
                "enriched_description": record.enriched_description,
                "validation": record.enrichment_validation,
                "status": record.enrichment_status,
                "error": record.enrichment_error,
                "prompt_version": record.enrichment_version,
            }
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
    return len(ids)


def run_embedding_stage(
    *,
    limit: int = 100,
    session_factory: sessionmaker[Session] = SESSION_FACTORY,
) -> int:
    """Embed validated enriched descriptions; invoked only as a separate stage."""
    from toolmeta_harvester.tasks.embedding import embed

    model = "nomic-embed-text-v2-moe"
    embedding_type = "enriched_description"
    with session_factory() as session:
        records = session.scalars(
            select(ToolMetadata)
            .where(
                ToolMetadata.enrichment_status == "validated",
                ToolMetadata.enriched_description.is_not(None),
            )
            .order_by(func.md5(cast(ToolMetadata.id, String)), ToolMetadata.id)
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
            model=model,
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
                "tool_id": record.id,
                "embedding_type": embedding_type,
                "embedding_model": model,
                "text": record.enriched_description,
                "vector": vector,
            }
            for record, vector in zip(records, vectors)
        ]
        statement = insert(ToolEmbedding).values(rows)
        session.execute(
            statement.on_conflict_do_update(
                constraint="uq_tool_embedding",
                set_={
                    "text": statement.excluded.text,
                    "vector": statement.excluded.vector,
                    "created_at": func.now(),
                },
            )
        )
        session.commit()
    return len(records)
