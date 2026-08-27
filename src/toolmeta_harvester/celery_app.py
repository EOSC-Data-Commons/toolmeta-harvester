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

celery_app.conf.imports = ("toolmeta_harvester.celery_tasks",)
