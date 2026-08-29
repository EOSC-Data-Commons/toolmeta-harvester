from __future__ import annotations

import argparse

from toolmeta_harvester.celery_tasks import (
    harvest_url_task,
)


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "url",
        help="URL to harvest via Celery",
    )

    args = parser.parse_args()

    task = harvest_url_task.delay(args.url)

    print(f"Queued Celery task: {task.id}")


if __name__ == "__main__":
    main()
