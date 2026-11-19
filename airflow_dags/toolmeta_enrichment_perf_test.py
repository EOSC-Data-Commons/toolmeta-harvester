import asyncio
import logging
import statistics
import time
from datetime import timedelta

from airflow.sdk import dag, task, Param
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from toolmeta_harvester.config import egi_llm_api_key, llm_api
from toolmeta_harvester.db.engine import engine
from toolmeta_harvester.db.models import ToolMetadata
from toolmeta_harvester.tasks.enrichment.llm import enrich_tool_metadata

logger = logging.getLogger(__name__)


@dag(
    dag_id="toolmeta_test_llm_enrichment",
    schedule=None,
    catchup=False,
    params={
        "num_tools": Param(
            100,
            type="integer",
            minimum=1,
            maximum=5000,
            description="Number of random tools to enrich",
        ),
    },
    tags=["llm", "test"],
)
def test_llm_enrichment():

    @task(execution_timeout=timedelta(hours=1))
    def enrich_random_tools(**context):
        num_tools = context["params"]["num_tools"]

        # Select random tools without modifying the database.
        with Session(engine) as session:
            records = session.execute(
                select(
                    ToolMetadata.id,
                    ToolMetadata.raw_metadata,
                )
                .where(ToolMetadata.raw_metadata.is_not(None))
                .order_by(func.random())
                .limit(num_tools)
            ).all()

        logger.info("Selected %d random tools", len(records))

        async def run_enrichment():
            durations = []
            failures = 0
            total_start = time.perf_counter()

            endpoint_url = llm_api()
            api_key = egi_llm_api_key()

            for tool_id, raw_metadata in records:
                start = time.perf_counter()

                try:
                    description = await enrich_tool_metadata(
                        raw_metadata=raw_metadata,
                        endpoint_url=endpoint_url,
                        api_key=api_key,
                    )

                    elapsed = time.perf_counter() - start

                    if not description or not description.strip():
                        failures += 1
                        logger.warning(
                            "No enrichment for tool %s (%.2fs)",
                            tool_id,
                            elapsed,
                        )
                        continue

                    durations.append(elapsed)

                    logger.info(
                        "Tool: %s | Duration: %.2fs\nEnrichment:\n%s",
                        tool_id,
                        elapsed,
                        description,
                    )

                except Exception:
                    elapsed = time.perf_counter() - start
                    failures += 1
                    logger.exception(
                        "Enrichment failed for tool %s after %.2fs",
                        tool_id,
                        elapsed,
                    )

            total_elapsed = time.perf_counter() - total_start
            successful = len(durations)

            logger.info("=== LLM Enrichment Performance ===")
            logger.info("Tools attempted: %d", len(records))
            logger.info("Successful: %d", successful)
            logger.info("Failed/empty: %d", failures)
            logger.info("Total wall time: %.2fs", total_elapsed)

            if durations:
                logger.info(
                    "Mean latency: %.2fs",
                    statistics.mean(durations),
                )
                logger.info(
                    "Median latency: %.2fs",
                    statistics.median(durations),
                )
                logger.info(
                    "Min latency: %.2fs",
                    min(durations),
                )
                logger.info(
                    "Max latency: %.2fs",
                    max(durations),
                )
                logger.info(
                    "Throughput: %.2f enrichments/min",
                    successful / total_elapsed * 60,
                )

            return {
                "attempted": len(records),
                "successful": successful,
                "failed": failures,
                "total_seconds": round(total_elapsed, 2),
                "enrichments_per_minute": (
                    round(successful / total_elapsed * 60, 2)
                    if total_elapsed > 0
                    else 0
                ),
            }

        return asyncio.run(run_enrichment())

    enrich_random_tools()


test_llm_enrichment()
