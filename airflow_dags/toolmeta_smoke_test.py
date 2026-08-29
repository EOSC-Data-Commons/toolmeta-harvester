from airflow.sdk import dag, task


@dag(
    dag_id="toolmeta_smoke_test",
    schedule=None,
    catchup=False,
    tags=["test", "tool-harvester"],
)
def test_toolmeta_import():

    @task
    def test_import():
        import toolmeta_harvester
        from toolmeta_harvester.api import harvest_url

        return {
            "package": toolmeta_harvester.__name__,
            "path": str(toolmeta_harvester.__path__[0]),
            "harvest_url": str(harvest_url),
        }

    test_import()


test_toolmeta_import()
