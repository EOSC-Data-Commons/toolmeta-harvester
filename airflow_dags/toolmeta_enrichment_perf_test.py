import asyncio
import logging
import statistics
import time
import uuid
from datetime import timedelta

from airflow.sdk import dag, task, Param
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from toolmeta_harvester.config import egi_llm_api_key, llm_api
from toolmeta_harvester.db.engine import engine
from toolmeta_harvester.db.models import ToolMetadata
from toolmeta_harvester.tasks.enrichment.llm import enrich_tool_metadata

logger = logging.getLogger(__name__)

BATCH_SIZE = 50
MAX_ACTIVE_BATCHES = 4


@dag(
    dag_id="test_llm_enrichment",
    schedule=None,
    catchup=False,
    max_active_runs=1,
    max_active_tasks=10,
    params={
        "num_tools": Param(
            1000,
            type="integer",
            minimum=1,
            maximum=10000,
            description="Number of random tools to enrich",
        ),
    },
    tags=["llm", "test", "benchmark"],
)
def test_llm_enrichment():

    @task
    def create_batches(**context) -> list[list[str]]:
        num_tools = context["params"]["num_tools"]

        with Session(engine) as session:
            tool_ids = session.scalars(
                select(ToolMetadata.id)
                .where(ToolMetadata.raw_metadata.is_not(None))
                .order_by(func.random())
                .limit(num_tools)
            ).all()

        ids = [str(tool_id) for tool_id in tool_ids]

        batches = [ids[i : i + BATCH_SIZE] for i in range(0, len(ids), BATCH_SIZE)]

        logger.info(
            "Selected %d random tools in %d batches",
            len(ids),
            len(batches),
        )

        return batches

    @task(
        retries=0,
        max_active_tis_per_dag=MAX_ACTIVE_BATCHES,
        execution_timeout=timedelta(hours=2),
    )
    def enrich_batch(tool_ids: list[str]) -> dict:
        ids = [uuid.UUID(tool_id) for tool_id in tool_ids]

        with Session(engine) as session:
            records = session.execute(
                select(
                    ToolMetadata.id,
                    ToolMetadata.raw_metadata,
                ).where(ToolMetadata.id.in_(ids))
            ).all()

        async def run_enrichment():
            durations = []
            failures = 0
            start_total = time.perf_counter()

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
                            "Empty enrichment: %s (%.2fs)",
                            tool_id,
                            elapsed,
                        )
                        continue

                    durations.append(elapsed)

                    logger.debug(
                        "Tool: %s | Duration: %.2fs\nEnrichment:\n%s",
                        tool_id,
                        elapsed,
                        description,
                    )

                except Exception:
                    elapsed = time.perf_counter() - start
                    failures += 1
                    logger.exception(
                        "Enrichment failed for %s after %.2fs",
                        tool_id,
                        elapsed,
                    )

            total_elapsed = time.perf_counter() - start_total
            successful = len(durations)

            logger.info("=== Batch Performance ===")
            logger.info("Attempted: %d", len(records))
            logger.info("Successful: %d", successful)
            logger.info("Failed: %d", failures)
            logger.info("Wall time: %.2fs", total_elapsed)

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
                "llm_api_url": endpoint_url,
                "attempted": len(records),
                "successful": successful,
                "failed": failures,
                "wall_seconds": total_elapsed,
                "latencies": durations,
            }

        return asyncio.run(run_enrichment())

    @task
    def summarize_performance(results: list[dict]):
        attempted = sum(r["attempted"] for r in results)
        successful = sum(r["successful"] for r in results)
        failed = sum(r["failed"] for r in results)

        all_latencies = [
            latency for result in results for latency in result["latencies"]
        ]

        batch_times = [r["wall_seconds"] for r in results]

        # Approximation: assumes batches execute concurrently
        # in groups of MAX_ACTIVE_BATCHES.
        estimated_wall_time = sum(batch_times) / MAX_ACTIVE_BATCHES

        logger.info("=== Overall LLM Performance ===")
        logger.info(
            "LLM API URL: %s",
            ", ".join(sorted({r["llm_api_url"] for r in results})),
        )
        logger.info("Batches: %d", len(results))
        logger.info("Attempted: %d", attempted)
        logger.info("Successful: %d", successful)
        logger.info("Failed: %d", failed)

        if all_latencies:
            logger.info(
                "Mean latency: %.2fs",
                statistics.mean(all_latencies),
            )
            logger.info(
                "Median latency: %.2fs",
                statistics.median(all_latencies),
            )
            logger.info(
                "Min latency: %.2fs",
                min(all_latencies),
            )
            logger.info(
                "Max latency: %.2fs",
                max(all_latencies),
            )

        logger.info(
            "Estimated wall time: %.2fs",
            estimated_wall_time,
        )

        if estimated_wall_time > 0:
            logger.info(
                "Estimated throughput: %.2f enrichments/min",
                successful / estimated_wall_time * 60,
            )

    batches = create_batches()
    results = enrich_batch.expand(tool_ids=batches)
    summarize_performance(results)


test_llm_enrichment()
