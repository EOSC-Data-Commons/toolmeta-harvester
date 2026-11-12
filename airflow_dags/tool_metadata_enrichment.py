from __future__ import annotations

import os
from datetime import timedelta
from pathlib import Path

from airflow.sdk import Asset, dag, get_current_context, task

ENRICHED_DESCRIPTIONS = Asset("toolmeta://enriched-descriptions")
DEFAULT_SAMPLE = (
    "experiments/2026-11-03_0218_representative-100_extraction-comparison/"
    "representative_sample_100.json"
)
TOOLMETA_ROOT = Path(
    os.environ.get("TOOLMETA_HARVESTER_ROOT", "/opt/airflow/toolmeta-harvester-source")
)


def _sample_path(config: dict) -> Path:
    path = Path(config.get("sample_path", DEFAULT_SAMPLE))
    return path if path.is_absolute() else TOOLMETA_ROOT / path


@dag(
    dag_id="tool_metadata_enrichment",
    schedule=None,
    catchup=False,
    max_active_runs=1,
    tags=["toolmeta", "enrichment", "experiment"],
    doc_md="""
    Generate one variant from the immutable representative sample.

    Trigger with `experiment_id`, `variant` (`A` or `B`), and optionally
    `sample_path`. Variant A generates directly from source metadata; variant
    B first extracts a structured semantic profile. Both variants write a
    distinct row for each sampled tool and emit the enrichment Asset event.
    """,
)
def tool_metadata_enrichment():
    @task(
        retries=1,
        retry_delay=timedelta(minutes=2),
        outlets=[ENRICHED_DESCRIPTIONS],
    )
    def enrich_representative_sample() -> dict:
        from toolmeta_harvester.enrichment.pipeline import run_enrichment_sample

        context = get_current_context()
        config = context["dag_run"].conf or {}
        experiment_id = config.get("experiment_id")
        variant = config.get("variant")
        if not experiment_id or variant not in {"A", "B"}:
            raise ValueError("DAG run config requires experiment_id and variant A or B")
        result = run_enrichment_sample(
            experiment_id=experiment_id,
            variant=variant,
            sample_path=_sample_path(config),
        )
        context["outlet_events"][ENRICHED_DESCRIPTIONS].extra = {
            "experiment_id": str(experiment_id),
            "variant": variant,
            "sample_path": str(_sample_path(config)),
        }
        return result

    enrich_representative_sample()


tool_metadata_enrichment()
