from __future__ import annotations

import argparse
import json

from toolmeta_harvester.api import harvest_url


def main():
    parser = argparse.ArgumentParser(
        description="Manually test harvesting a single URL"
    )

    parser.add_argument(
        "url",
        help="URL to harvest",
    )

    args = parser.parse_args()

    run = harvest_url(args.url)

    output = {
        "harvest_run_id": str(run.id),
        "source": run.source,
        "status": run.status,
        "harvested_count": run.harvested_count,
        "failed_count": run.failed_count,
    }

    print(
        json.dumps(
            output,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
