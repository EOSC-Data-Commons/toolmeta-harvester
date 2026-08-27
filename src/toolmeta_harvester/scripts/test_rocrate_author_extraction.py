from __future__ import annotations

import argparse
import json
from datetime import date, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from toolmeta_harvester.db.engine import engine
from toolmeta_harvester.db.models import ToolMetadata
from toolmeta_harvester.extractors.extract_ro_crate_metadata import (
    extract_ro_crate_metadata,
)


def json_default(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()

    if isinstance(value, UUID):
        return str(value)

    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def test_extraction(source_identifier: str) -> None:
    with Session(engine) as session:
        records = session.scalars(
            select(ToolMetadata).where(
                ToolMetadata.source_identifier == source_identifier
            )
        ).all()

        if not records:
            raise SystemExit(
                f"No record found for source_identifier={source_identifier!r}"
            )

        for record in records:
            print(f"\n=== {record.title} (id={record.id}) ===")

            if not record.raw_metadata:
                print("No raw_metadata available")
                continue

            extracted = extract_ro_crate_metadata(record.raw_metadata)

            print("\nStored authors:")
            print(
                json.dumps(
                    record.authors,
                    indent=2,
                    ensure_ascii=False,
                    default=json_default,
                )
            )

            print("\nRe-extracted authors:")
            print(
                json.dumps(
                    extracted.get("authors", []),
                    indent=2,
                    ensure_ascii=False,
                    default=json_default,
                )
            )


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Test RO-Crate metadata extraction against "
            "existing PostgreSQL raw_metadata without updating records."
        )
    )

    parser.add_argument(
        "source_identifier",
        help="ToolMetadata source_identifier",
    )

    args = parser.parse_args()

    test_extraction(args.source_identifier)


if __name__ == "__main__":
    main()
