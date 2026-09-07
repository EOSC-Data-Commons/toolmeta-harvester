from __future__ import annotations

import argparse
import json
from datetime import date, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from toolmeta_harvester.db.engine import engine
from toolmeta_harvester.db.models import ToolMetadata


def json_default(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()

    if isinstance(value, UUID):
        return str(value)

    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def model_to_dict(record: ToolMetadata) -> dict:
    return {
        column.name: getattr(record, column.name) for column in record.__table__.columns
    }


def dump_tool_metadata(source_identifier: str) -> None:
    with Session(engine) as session:
        records = session.scalars(
            select(ToolMetadata).where(
                ToolMetadata.source_identifier == source_identifier
            )
        ).all()

        if not records:
            raise SystemExit(
                f"No tool_metadata record found for "
                f"source_identifier={source_identifier!r}"
            )

        data = [model_to_dict(record) for record in records]

        # Return a single object when there is only one match.
        output = data[0] if len(data) == 1 else data

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
        description=("Dump PostgreSQL tool_metadata record(s) as JSON")
    )

    parser.add_argument(
        "source_identifier",
        help="Source identifier to look up",
    )

    args = parser.parse_args()

    dump_tool_metadata(args.source_identifier)


if __name__ == "__main__":
    main()
