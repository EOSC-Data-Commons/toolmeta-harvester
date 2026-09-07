import os
import re
from urllib.parse import urlparse

from airflow.sdk import dag, task
from sqlalchemy import create_engine, text, URL
from toolmeta_harvester.flows.registry import get_dynamic_flows


DATABASE_URL = URL.create(
    drivername="postgresql+psycopg",
    username=os.environ["TOOLMETA_HARVESTER_DATABASE__USER"],
    password=os.environ["TOOLMETA_HARVESTER_DATABASE__PASSWORD"],
    host=os.environ["TOOLMETA_HARVESTER_DATABASE__HOST"],
    port=int(os.environ["TOOLMETA_HARVESTER_DATABASE__PORT"]),
    database=os.environ["TOOLMETA_HARVESTER_DATABASE__NAME"],
)


def find_flow_for_url(url: str):
    hostname = urlparse(url).hostname

    for flow in get_dynamic_flows():
        print(
            "FLOW:",
            flow.name,
            "hosts=",
            flow.hosts,
            "matcher=",
            flow.matcher,
        )
        if hostname in flow.hosts:
            return flow

        if flow.matcher:
            matched = flow.matcher(url)
            print(
                "MATCH:",
                flow.name,
                url,
                matched,
                flush=True,
            )
            if matched:
                return flow

    raise ValueError(f"No dynamic harvester supports URL: {url}")


def load_sources() -> list[dict]:
    engine = create_engine(DATABASE_URL)

    try:
        with engine.connect() as conn:
            result = conn.execute(
                text("""
                    SELECT
                        id,
                        url,
                        schedule,
                        enabled
                    FROM harvest_source
                    WHERE enabled = true
                    ORDER BY id
                """)
            )

            return [dict(row._mapping) for row in result]
    finally:
        engine.dispose()


def make_dag_id(url: str) -> str:
    parsed = urlparse(url)

    hostname = parsed.hostname or "unknown"
    hostname = re.sub(r"[^A-Za-z0-9_-]", "_", hostname)

    record_id = parsed.path.rstrip("/").split("/")[-1]
    record_id = re.sub(r"[^A-Za-z0-9_-]", "_", record_id)

    return f"harvest_{hostname}_{record_id}"


def create_dynamic_dag(
    *,
    dag_id: str,
    url: str,
    handler,
    schedule: str | None,
    enabled: bool,
):
    @dag(
        dag_id=f"tool_{dag_id}",
        schedule=schedule,
        catchup=False,
        max_active_runs=1,
        is_paused_upon_creation=not enabled,
        tags=[
            "tool-harvester",
            "dynamic",
        ],
    )
    def harvest_dag():

        @task
        def harvest():
            result = handler(url)

            return {
                "pipeline_tag": result.pipeline_tag,
                "record_ids": result.record_ids,
                "harvested_count": result.harvested_count,
                "failed_count": result.failed_count,
            }

        harvest()

    return harvest_dag()


# def create_harvest_dag(
#     dag_id: str,
#     url: str,
#     schedule: str | None,
#     enabled: bool = True,
# ):
#     @dag(
#         dag_id=dag_id,
#         schedule=schedule,
#         catchup=False,
#         max_active_runs=1,
#         is_paused_upon_creation=not enabled,
#         tags=["tool-harvester"],
#     )
#     def harvest_dag():
#
#         @task
#         def harvest():
#             from toolmeta_harvester.api import harvest_url
#
#             result = harvest_url(url)
#
#             return {
#                 "pipeline_tag": result.pipeline_tag,
#                 "record_ids": result.record_ids,
#                 "harvested_count": result.harvested_count,
#                 "failed_count": result.failed_count,
#             }
#
#         harvest()
#
#     return harvest_dag()

for source in load_sources():
    flow = find_flow_for_url(source["url"])

    dag_id = make_dag_id(source["url"])

    schedule = source["schedule"] or flow.default_schedule

    globals()[dag_id] = create_dynamic_dag(
        dag_id=dag_id,
        url=source["url"],
        handler=flow.handler,
        schedule=schedule,
        enabled=source["enabled"],
    )
