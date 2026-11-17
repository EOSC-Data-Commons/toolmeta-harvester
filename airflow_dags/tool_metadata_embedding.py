from datetime import timedelta

from airflow.sdk import Asset, dag, get_current_context, task

ENRICHED_DESCRIPTIONS = Asset("toolmeta://enriched-descriptions")


@dag(
    dag_id="tool_metadata_embedding",
    schedule=ENRICHED_DESCRIPTIONS,
    catchup=False,
    max_active_runs=1,
    max_active_tasks=4,
    tags=["toolmeta", "embedding"],
    doc_md="""Create missing vectors for current successful generated descriptions.

    This DAG consumes one Asset event after an enrichment run's mapped batches finish. It maps
    pending results into batches of 10, with an embedding API batch size of 16. Validation is
    not a prerequisite. Manually trigger with `{"limit": 1000}` for a bounded backfill, or
    `{"full_catalog": true}` to process all currently eligible results.
    """,
)
def tool_metadata_embedding():
    @task(retries=0)
    def prepare_batches() -> list[list[str]]:
        from toolmeta_harvester.enrichment import select_pending_embedding_batches

        context = get_current_context()
        conf = context["dag_run"].conf or {}
        unknown = set(conf) - {"limit", "full_catalog"}
        if unknown:
            raise ValueError(f"Unsupported embedding parameters: {sorted(unknown)}")
        full_catalog = bool(conf.get("full_catalog", True))
        if full_catalog and "limit" in conf:
            raise ValueError("Do not provide limit when full_catalog is true")
        return select_pending_embedding_batches(
            limit=None if full_catalog else conf.get("limit"),
            full_catalog=full_catalog,
            batch_size=10,
        )

    @task(retries=1, execution_timeout=timedelta(hours=3))
    def embed_batch(enrichment_ids: list[str]) -> dict:
        from toolmeta_harvester.enrichment import embed_enrichment_batch

        return embed_enrichment_batch(enrichment_ids=enrichment_ids)

    @task(retries=0)
    def summarize_batches(batch_summaries: list[dict]) -> dict:
        return {
            "selected_records": sum(
                item["selected_records"] for item in batch_summaries
            ),
            "embeddings_written": sum(
                item["embeddings_written"] for item in batch_summaries
            ),
            "llm_requests": sum(item["llm_requests"] for item in batch_summaries),
            "processing_seconds": round(
                sum(item["processing_seconds"] for item in batch_summaries), 3
            ),
        }

    results = embed_batch.expand(enrichment_ids=prepare_batches())
    summarize_batches(results)


tool_metadata_embedding()
