from __future__ import annotations

from datetime import timedelta

from airflow.exceptions import AirflowFailException
from airflow.sdk import Asset, dag, get_current_context, task

ENRICHED_DESCRIPTIONS = Asset("toolmeta://enriched-descriptions")


@dag(
    dag_id="toolmeta_enrich_description",
    schedule=None,
    catchup=False,
    max_active_runs=1,
    max_active_tasks=4,
    tags=["toolmeta", "enrichment"],
    doc_md="""Manually generate descriptions from raw metadata with one LLM call per record.

    Configuration: `{"limit": 100}` (default bounded sample), `{"tool_ids": [...]}` for
    an explicit set, or `{"full_catalog": true}` for an intentional catalog run. Generation
    does not run extraction or LLM validation. Successful metadata changes emit an Asset event
    consumed by the embedding DAG. Airflow run IDs are persisted with attempts.
    """,
)
def tool_metadata_enrichment():
    @task(retries=0)
    def prepare_batches() -> list[dict]:
        from toolmeta_harvester.enrichment import select_enrichment_batches

        context = get_current_context()
        conf = context["dag_run"].conf or {}
        if not isinstance(conf, dict):
            raise TypeError("DAG run configuration must be an object")
        unknown = set(conf) - {"tool_ids", "limit", "full_catalog"}
        if unknown:
            raise ValueError(f"Unsupported enrichment parameters: {sorted(unknown)}")
        full_catalog = bool(conf.get("full_catalog", False))
        tool_ids = conf.get("tool_ids")
        if tool_ids is not None and (full_catalog or "limit" in conf):
            raise ValueError("tool_ids cannot be combined with limit or full_catalog")
        if full_catalog and "limit" in conf:
            raise ValueError("Do not provide limit when full_catalog is true")
        batches = select_enrichment_batches(
            tool_ids=tool_ids,
            limit=None
            if full_catalog or tool_ids is not None
            else conf.get("limit", 100),
            full_catalog=full_catalog,
            batch_size=10,
        )
        return [
            {"tool_ids": batch, "run_id": context["dag_run"].run_id}
            for batch in batches
        ]

    @task(retries=0, execution_timeout=timedelta(hours=3))
    def enrich_batch(batch: dict) -> dict:
        from toolmeta_harvester.enrichment import run_enrichment

        return run_enrichment(tool_ids=batch["tool_ids"], run_id=batch["run_id"])

    results = enrich_batch.expand(batch=prepare_batches())

    @task(retries=0, outlets=[ENRICHED_DESCRIPTIONS])
    def summarize_batches(batch_summaries: list[dict]) -> dict:
        context = get_current_context()
        totals = {
            "selected_records": sum(
                item["selected_records"] for item in batch_summaries
            ),
            "generated": sum(item["generated"] for item in batch_summaries),
            "skipped_empty_metadata": sum(
                item["skipped_empty_metadata"] for item in batch_summaries
            ),
            "insufficient_metadata": sum(
                item["insufficient_metadata"] for item in batch_summaries
            ),
            "failed": sum(item["failed"] for item in batch_summaries),
            "up_to_date": sum(item["up_to_date"] for item in batch_summaries),
            "skipped_inflight": sum(
                item["skipped_inflight"] for item in batch_summaries
            ),
            "llm_requests": sum(item["llm_requests"] for item in batch_summaries),
        }
        context["outlet_events"][ENRICHED_DESCRIPTIONS].extra = {
            "run_id": context["dag_run"].run_id,
            **totals,
        }
        return totals

    totals = summarize_batches(results)

    @task(retries=0)
    def fail_on_record_errors(summary: dict) -> None:
        if summary["failed"]:
            raise AirflowFailException(
                f"Enrichment had {summary['failed']} record failure(s); use the processing report to review and retry them."
            )

    fail_on_record_errors(totals)


tool_metadata_enrichment()
