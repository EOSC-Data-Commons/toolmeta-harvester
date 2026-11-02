import os
from urllib.parse import urlparse

from airflow.sdk import dag, task
from sqlalchemy import create_engine, text, select
from sqlalchemy.orm import Session

from toolmeta_harvester.flows.registry import get_dynamic_flows
from toolmeta_harvester.db import database
from toolmeta_harvester.db.engine import engine
from toolmeta_harvester.db.models import HarvestSource


def find_flow_for_url(url: str):
    hostname = urlparse(url).hostname

    for flow in get_dynamic_flows():
        if hostname in flow.hosts:
            return flow

        if flow.matcher and flow.matcher(url):
            return flow

    raise ValueError(f"No dynamic harvester supports URL: {url}")


@dag(
    dag_id="toolmeta_dynamic_harvest",
    schedule="0 20 * * 6",
    catchup=False,
    max_active_runs=1,
    max_active_tasks=4,
    tags=["tool-harvester", "dynamic"],
)
def dynamic_harvest_dag():
    @task
    def initialize_db():
        database.initialize_db()

    @task
    def load_sources() -> list[str]:
        with Session(engine) as session:
            stmt = (
                select(HarvestSource.url)
                .where(HarvestSource.enabled.is_(True))
                .order_by(HarvestSource.id)
            )

            return list(session.scalars(stmt))

    @task(
        max_active_tis_per_dag=4,
        retries=2,
    )
    def harvest(url: str):
        flow = find_flow_for_url(url)

        result = flow.handler(url)

        return {
            "url": url,
            "pipeline_tag": result.pipeline_tag,
            "record_ids": result.record_ids,
            "harvested_count": result.harvested_count,
            "failed_count": result.failed_count,
        }

    init = initialize_db()
    sources = load_sources()
    harvest_tasks = harvest.expand(
        url=sources,
    )
    init >> sources >> harvest_tasks


dynamic_harvest_dag()
