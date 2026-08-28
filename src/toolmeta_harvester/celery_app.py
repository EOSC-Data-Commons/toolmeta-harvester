# toolmeta_harvester/celery_app.py

import os
from dotenv import load_dotenv

from celery import Celery

load_dotenv()


celery_app = Celery(
    "toolmeta_harvester",
    broker=os.getenv(
        "CELERY_BROKER_URL",
        "amqp://guest:guest@rabbitmq:5672//",
    ),
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    control_queue_durable=False,
    control_queue_exclusive=True,
    event_queue_durable=False,
    event_queue_exclusive=True,
)

celery_app.conf.imports = ("toolmeta_harvester.celery_tasks",)
