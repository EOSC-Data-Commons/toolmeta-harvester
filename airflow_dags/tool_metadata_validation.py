from airflow.sdk import dag, get_current_context, task


@dag(
    dag_id="tool_metadata_validation",
    schedule=None,
    catchup=False,
    max_active_runs=1,
    tags=["toolmeta", "validation", "manual"],
    doc_md="""Optional LLM review of selected generated descriptions. It runs independently and
    never changes generated text or gates enrichment or embedding. Supply `tool_ids`,
    `enrichment_ids`, or a bounded `limit` (default 100, maximum 1000).
    """,
)
def tool_metadata_validation():
    @task(retries=0)
    def validate_selected_results() -> dict:
        from toolmeta_harvester.enrichment import run_validation

        context = get_current_context()
        conf = context["dag_run"].conf or {}
        unknown = set(conf) - {"tool_ids", "enrichment_ids", "limit"}
        if unknown:
            raise ValueError(f"Unsupported validation parameters: {sorted(unknown)}")
        return run_validation(
            tool_ids=conf.get("tool_ids"),
            enrichment_ids=conf.get("enrichment_ids"),
            limit=conf.get("limit", 100),
            run_id=context["dag_run"].run_id,
        )

    validate_selected_results()


tool_metadata_validation()
