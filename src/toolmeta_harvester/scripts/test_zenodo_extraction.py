from __future__ import annotations

import argparse
import json
from datetime import date, datetime
from uuid import UUID

from toolmeta_harvester.extractors.tool_metadata import (
    extract_tool_metadata,
)
from toolmeta_harvester.tasks.zenodo_jsonld import (
    parse_zenodo_url,
    download_zenodo_jsonld,
)


def json_default(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()

    if isinstance(value, UUID):
        return str(value)

    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def test_zenodo_extraction(
    zenodo_url: str,
) -> None:
    """
    Fetch Zenodo JSON-LD and print normalized ScienceToolMeta.

    No PostgreSQL writes are performed.
    """

    record_id = parse_zenodo_url(zenodo_url)

    raw_metadata, metadata_url = download_zenodo_jsonld(record_id)

    tool_metadata = extract_tool_metadata(raw_metadata)

    output = {
        "source": {
            "record_id": record_id,
            "source_url": zenodo_url,
            "metadata_url": metadata_url,
        },
        "tool_metadata": tool_metadata,
    }

    print(
        json.dumps(
            output,
            indent=2,
            ensure_ascii=False,
            default=json_default,
        )
    )


def main():
    parser = argparse.ArgumentParser(
        description=("Fetch Zenodo JSON-LD and print normalized ScienceToolMeta.")
    )

    parser.add_argument(
        "url",
        help=("Zenodo record URL, e.g. https://zenodo.org/records/22096936"),
    )

    args = parser.parse_args()

    test_zenodo_extraction(args.url)


if __name__ == "__main__":
    main()
