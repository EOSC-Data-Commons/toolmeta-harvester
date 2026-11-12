from airflow.sdk import Asset, dag, task

ENRICHED_DESCRIPTIONS = Asset("toolmeta://enriched-descriptions")


@dag(
    dag_id="tool_metadata_embedding",
    schedule=ENRICHED_DESCRIPTIONS,
    catchup=False,
    max_active_runs=1,
    tags=["toolmeta", "embedding"],
    doc_md="""
    Embed every completed enriched description that does not yet have a vector.

    This DAG is scheduled from the enrichment Asset and does not depend on
    validation. The library links each vector to its exact enrichment row.
    """,
)
def tool_metadata_embedding():
    @task(retries=1)
    def embed_pending_results() -> dict:
        from toolmeta_harvester.enrichment.pipeline import embed_pending_enrichments

        return embed_pending_enrichments()

    embed_pending_results()


tool_metadata_embedding()
