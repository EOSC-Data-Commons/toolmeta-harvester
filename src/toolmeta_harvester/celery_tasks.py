from toolmeta_harvester.api import harvest_url
from toolmeta_harvester.celery_app import celery_app


@celery_app.task(name="toolmeta.harvest_url")
def harvest_url_task(
    url: str,
) -> dict:
    run = harvest_url(url)

    return {
        "harvest_run_id": str(run.id),
        "status": run.status,
    }
