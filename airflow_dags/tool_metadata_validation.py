from __future__ import annotations

import os
from pathlib import Path

from airflow.sdk import dag, get_current_context, task

DEFAULT_SAMPLE = (
    "experiments/2026-11-03_0218_representative-100_extraction-comparison/"
    "representative_sample_100.json"
)
TOOLMETA_ROOT = Path(
    os.environ.get("TOOLMETA_HARVESTER_ROOT", "/opt/airflow/toolmeta-harvester-source")
)


@dag(
    dag_id="tool_metadata_validation",
    schedule=None,
    catchup=False,
    max_active_runs=1,
    tags=["toolmeta", "validation"],
    doc_md="""
    Independently validate one completed enrichment variant.

    Deterministic checks are stored with the enrichment result. This DAG adds
    supplementary LLM-as-judge scores and issues; neither validation level is
    a gate for the embedding DAG.
    """,
)
def tool_metadata_validation():
    @task(retries=1)
    def validate_representative_sample() -> dict:
        from toolmeta_harvester.enrichment.pipeline import run_validation_sample

        context = get_current_context()
        config = context["dag_run"].conf or {}
        experiment_id = config.get("experiment_id")
        variant = config.get("variant")
        if not experiment_id or variant not in {"A", "B"}:
            raise ValueError("DAG run config requires experiment_id and variant A or B")
        sample_path = Path(config.get("sample_path", DEFAULT_SAMPLE))
        if not sample_path.is_absolute():
            sample_path = TOOLMETA_ROOT / sample_path
        return run_validation_sample(
            experiment_id=experiment_id,
            variant=variant,
            sample_path=sample_path,
        )

    validate_representative_sample()


tool_metadata_validation()
