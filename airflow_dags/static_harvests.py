from airflow.sdk import dag, task

from toolmeta_harvester.flows.registry import get_static_flows


def create_static_dag(flow):
    @dag(
        dag_id=f"harvest_{flow.name}",
        schedule=flow.default_schedule,
        catchup=False,
        max_active_runs=1,
        tags=["tool-harvester", "static"],
    )
    def harvest_dag():
        @task
        def harvest():
            result = flow.handler()

            return {
                "pipeline_tag": result.pipeline_tag,
                "record_ids": result.record_ids,
                "harvested_count": result.harvested_count,
                "failed_count": result.failed_count,
            }

        harvest()

    return harvest_dag()


def create_test_static_dag(flow):
    @dag(
        dag_id=f"harvest_{flow.name}_test",
        schedule=flow.default_schedule,
        catchup=False,
        max_active_runs=1,
        tags=["tool-harvester", "static"],
    )
    def harvest_dag():
        @task
        def harvest():
            result = flow.handler(limit=3)

            return {
                "pipeline_tag": result.pipeline_tag,
                "record_ids": result.record_ids,
                "harvested_count": result.harvested_count,
                "failed_count": result.failed_count,
            }

        harvest()

    return harvest_dag()


for flow in get_static_flows():
    dag_id = f"harvest_{flow.name}"
    globals()[dag_id] = create_static_dag(flow)
    dag_id_test = f"harvest_{flow.name}_test"
    globals()[dag_id_test] = create_test_static_dag(flow)
