from datetime import UTC, datetime, timedelta

from airflow.sdk import dag, get_current_context, task


@dag(
    dag_id="tool_metadata_processing_report",
    schedule=None,
    catchup=False,
    max_active_runs=1,
    tags=["toolmeta", "reporting"],
    doc_md="""Summarize enrichment outcomes without making any LLM requests.

    Supply `run_id` to report one enrichment DAG run, or ISO timestamps `since` and `until`
    for a period. With neither, the default report covers the preceding day.
    """,
)
def tool_metadata_processing_report():
    @task(retries=0)
    def build_report() -> dict:
        from toolmeta_harvester.enrichment import processing_report

        context = get_current_context()
        conf = context["dag_run"].conf or {}
        run_id = conf.get("run_id")
        since = datetime.fromisoformat(conf["since"]) if conf.get("since") else None
        until = datetime.fromisoformat(conf["until"]) if conf.get("until") else None
        if not run_id and since is None and until is None:
            since = datetime.now(UTC) - timedelta(days=1)
        return processing_report(run_id=run_id, since=since, until=until)

    build_report()


tool_metadata_processing_report()
