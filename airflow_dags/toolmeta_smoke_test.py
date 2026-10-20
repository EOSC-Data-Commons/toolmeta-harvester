from airflow.sdk import dag, task


@dag(
    dag_id="toolmeta_smoke_test",
    schedule=None,
    catchup=False,
    tags=["test"],
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

    @task
    def test_initialize_db():
        from toolmeta_harvester.db import database

        database.initialize_db()

    t1 = test_import()
    t2 = test_initialize_db()

    t1 >> t2


test_toolmeta_import()
