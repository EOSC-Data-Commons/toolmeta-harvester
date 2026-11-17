import asyncio
import logging
import uuid

from airflow.sdk import dag, task
from sqlalchemy import select, func, or_
from sqlalchemy.orm import Session

from toolmeta_harvester.config import egi_llm_api_key, llm_api
from toolmeta_harvester.db.engine import engine
from toolmeta_harvester.db import database
from toolmeta_harvester.db.models import (
    ToolMetadata,
    ToolMetadataEnrichment,
)
from toolmeta_harvester.tasks.enrichment.llm import tool_metadata_enrichment
from toolmeta_harvester.tasks.enrichment.prompts.generation import MODEL, PROMPT_VERSION


logger = logging.getLogger(__name__)

LLM_API = llm_api()
EGI_LLM_API_KEY = egi_llm_api_key()

AIRFLOW_BATCH_SIZE = 50


@dag(
    dag_id="toolmeta_enrich_descriptions",
    schedule="0 3 * * 1",
    catchup=False,
    max_active_runs=1,
    max_active_tasks=10,
    tags=["llm", "enrichment"],
)
def enrich_descriptions():

    @task
    def initialize_db():
        database.initialize_db()

    @task
    def create_batches() -> list[list[str]]:
        """
        Find tools whose enrichment is missing or stale.

        An enrichment is stale when:
        - no enrichment exists for the current model/prompt, or
        - source metadata changed after the latest enrichment.
        """

        latest_enrichment = (
            select(
                ToolMetadataEnrichment.tool_id,
                func.max(ToolMetadataEnrichment.created_at).label("created_at"),
            )
            .where(
                ToolMetadataEnrichment.model == MODEL,
                ToolMetadataEnrichment.prompt_version == PROMPT_VERSION,
            )
            .group_by(ToolMetadataEnrichment.tool_id)
            .subquery()
        )

        with Session(engine) as session:
            stmt = (
                select(ToolMetadata.id)
                .outerjoin(
                    latest_enrichment,
                    latest_enrichment.c.tool_id == ToolMetadata.id,
                )
                .where(
                    ToolMetadata.raw_metadata.is_not(None),
                    or_(
                        latest_enrichment.c.tool_id.is_(None),
                        ToolMetadata.date_modified > latest_enrichment.c.created_at,
                    ),
                )
                .order_by(ToolMetadata.id)
            )

            tool_ids = session.scalars(stmt).all()

        ids = [str(tool_id) for tool_id in tool_ids]

        return [
            ids[i : i + AIRFLOW_BATCH_SIZE]
            for i in range(0, len(ids), AIRFLOW_BATCH_SIZE)
        ]

    @task(
        retries=2,
        max_active_tis_per_dag=4,
    )
    def enrich_batch(tool_ids: list[str]) -> int:
        ids = [uuid.UUID(tool_id) for tool_id in tool_ids]

        with Session(engine) as session:
            records = session.scalars(
                select(ToolMetadata)
                .where(ToolMetadata.id.in_(ids))
                .order_by(ToolMetadata.id)
            ).all()

            if not records:
                return 0

            async def enrich_records():
                results = []

                for record in records:
                    try:
                        description = (
                            await tool_metadata_enrichment.enrich_tool_metadata(
                                raw_metadata=record.raw_metadata,
                                endpoint_url=LLM_API,
                                api_key=EGI_LLM_API_KEY,
                            )
                        )

                        if description and description.strip():
                            results.append(
                                {
                                    "tool_id": record.id,
                                    "enriched_description": description.strip(),
                                    "model": MODEL,
                                    "prompt_version": PROMPT_VERSION,
                                }
                            )

                    except Exception:
                        logger.exception(
                            "Failed to enrich tool %s",
                            record.id,
                        )

                return results

            values = asyncio.run(enrich_records())

            if not values:
                return 0

            session.bulk_insert_mappings(
                ToolMetadataEnrichment,
                values,
            )
            session.commit()

            logger.info(
                "Enriched %d/%d tools",
                len(values),
                len(records),
            )

            return len(values)

    init = initialize_db()
    batches = create_batches()

    init >> batches

    enrich_batch.expand(tool_ids=batches)


enrich_descriptions()
