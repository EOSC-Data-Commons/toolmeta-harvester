import asyncio
import logging
import uuid
from datetime import timedelta

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
from toolmeta_harvester.tasks.enrichment.llm import enrich_tool_metadata
from toolmeta_harvester.tasks.enrichment.prompts.generation import (
    MODEL,
    PROMPT_VERSION,
)


logger = logging.getLogger(__name__)

LLM_API = llm_api()
EGI_LLM_API_KEY = egi_llm_api_key()

AIRFLOW_BATCH_SIZE = 50
TEST_MAX_TOOLS = 5


def create_enrichment_dag(
    dag_id: str,
    schedule: str | None,
    max_tools: int | None = None,
    batch_size: int = AIRFLOW_BATCH_SIZE,
    max_active_batches: int = 4,
    retries: int = 2,
):
    @dag(
        dag_id=dag_id,
        schedule=schedule,
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

            if max_tools is not None:
                stmt = stmt.limit(max_tools)

            with Session(engine) as session:
                tool_ids = session.scalars(stmt).all()

            ids = [str(tool_id) for tool_id in tool_ids]

            batches = [ids[i : i + batch_size] for i in range(0, len(ids), batch_size)]

            logger.info(
                "Prepared %d tools in %d batches (model=%s, prompt=%s, max_tools=%s)",
                len(ids),
                len(batches),
                MODEL,
                PROMPT_VERSION,
                max_tools,
            )

            return batches

        @task(
            retries=retries,
            retry_delay=timedelta(minutes=2),
            max_active_tis_per_dag=max_active_batches,
            execution_timeout=timedelta(hours=2),
        )
        def enrich_batch(tool_ids: list[str]) -> int:
            """Enrich a batch and persist successful descriptions."""

            ids = [uuid.UUID(tool_id) for tool_id in tool_ids]

            # Fetch metadata and detach it from the session
            # before making potentially slow LLM requests.
            with Session(engine) as session:
                records = session.execute(
                    select(
                        ToolMetadata.id,
                        ToolMetadata.raw_metadata,
                    )
                    .where(ToolMetadata.id.in_(ids))
                    .order_by(ToolMetadata.id)
                ).all()

            if not records:
                return 0

            async def enrich_records():
                results = []

                for tool_id, raw_metadata in records:
                    if not raw_metadata:
                        continue

                    try:
                        description = await enrich_tool_metadata(
                            raw_metadata=raw_metadata,
                            endpoint_url=LLM_API,
                            api_key=EGI_LLM_API_KEY,
                        )

                        if not description or not description.strip():
                            logger.info(
                                "No enrichment generated for tool %s",
                                tool_id,
                            )
                            continue

                        results.append(
                            {
                                "tool_id": tool_id,
                                "enriched_description": description.strip(),
                                "model": MODEL,
                                "prompt_version": PROMPT_VERSION,
                            }
                        )

                    except Exception:
                        logger.exception(
                            "Failed to enrich tool %s",
                            tool_id,
                        )

                return results

            values = asyncio.run(enrich_records())

            if not values:
                logger.info(
                    "No successful enrichments in batch of %d tools",
                    len(records),
                )
                return 0

            # Append-only: insert new successful enrichment records.
            # No UPSERT or deletion of previous generations.
            with Session(engine) as session:
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

    return enrich_descriptions()


# ---------------------------------------------------------
# Production DAG
# ---------------------------------------------------------

toolmeta_enrich_descriptions = create_enrichment_dag(
    dag_id="toolmeta_enrich_descriptions",
    schedule="0 3 * * 1",
    batch_size=AIRFLOW_BATCH_SIZE,
    max_active_batches=4,
    retries=2,
)


# ---------------------------------------------------------
# Test DAG
# ---------------------------------------------------------

toolmeta_enrich_descriptions_test = create_enrichment_dag(
    dag_id="toolmeta_enrich_descriptions_test",
    schedule=None,
    max_tools=TEST_MAX_TOOLS,
    batch_size=TEST_MAX_TOOLS,
    max_active_batches=1,
    retries=0,
)
