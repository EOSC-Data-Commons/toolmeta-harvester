import os
import subprocess
from pathlib import Path

from airflow.sdk import dag, get_current_context, task

TOOLMETA_ROOT = Path(
    os.environ.get("TOOLMETA_HARVESTER_ROOT", "/opt/airflow/toolmeta-harvester-source")
)
TOOLMETA_PYTHON = os.environ.get(
    "TOOLMETA_HARVESTER_PYTHON",
    "/opt/airflow/toolmeta-harvester-venv/bin/python",
)


def run_enrichment_stage(stage: str, run_id: str | None = None) -> None:
    """Run package business logic in its isolated Python 3.12 environment."""
    environment = os.environ.copy()
    source_path = str(TOOLMETA_ROOT / "src")
    environment["PYTHONPATH"] = os.pathsep.join(
        path for path in (source_path, environment.get("PYTHONPATH", "")) if path
    )
    command = [
        TOOLMETA_PYTHON,
        "-m",
        "toolmeta_harvester.enrichment.experiment",
        "--stage",
        stage,
    ]
    if run_id:
        command.extend(["--run-id", run_id])
    subprocess.run(
        command,
        cwd=TOOLMETA_ROOT,
        env=environment,
        check=True,
    )


@dag(
    dag_id="tool_metadata_enrichment_extraction",
    schedule=None,
    catchup=False,
    tags=["toolmeta", "enrichment", "extraction"],
)
def enrichment_extraction():
    @task
    def extract_sample():
        conf = get_current_context()["dag_run"].conf or {}
        run_enrichment_stage("extraction", conf.get("run_id"))

    extract_sample()


@dag(
    dag_id="tool_metadata_enrichment_generation",
    schedule=None,
    catchup=False,
    tags=["toolmeta", "enrichment", "generation"],
)
def enrichment_generation():
    @task
    def generate_sample():
        conf = get_current_context()["dag_run"].conf or {}
        run_enrichment_stage("generation", conf.get("run_id"))

    generate_sample()


@dag(
    dag_id="tool_metadata_enrichment_validation",
    schedule=None,
    catchup=False,
    tags=["toolmeta", "enrichment", "validation"],
)
def enrichment_validation():
    @task
    def validate_sample():
        conf = get_current_context()["dag_run"].conf or {}
        run_enrichment_stage("validation", conf.get("run_id"))

    validate_sample()


@dag(
    dag_id="toolmeta_enriched_description_embedding",
    schedule=None,
    catchup=False,
    tags=["toolmeta", "embedding"],
)
def enriched_description_embedding():
    @task
    def embed_sample():
        conf = get_current_context()["dag_run"].conf or {}
        run_enrichment_stage("embedding", conf.get("run_id"))

    embed_sample()


enrichment_extraction()
enrichment_generation()
enrichment_validation()
enriched_description_embedding()
