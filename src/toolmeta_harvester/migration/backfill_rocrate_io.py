from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from toolmeta_harvester.db.engine import engine
from toolmeta_harvester.db.models import ToolMetadata
from toolmeta_harvester.extractors.extract_ro_crate_metadata import (
    extract_ro_crate_metadata,
)

logger = logging.getLogger(__name__)


def backfill_inputs_outputs() -> None:
    updated = 0
    skipped = 0
    failed = 0

    with Session(engine) as session:
        records = session.scalars(
            select(ToolMetadata).where(ToolMetadata.metadata_format == "ro-crate")
        )

        for record in records:
            try:
                if not record.raw_metadata:
                    skipped += 1
                    continue

                metadata = extract_ro_crate_metadata(record.raw_metadata)

                record.inputs = metadata.get(
                    "inputs",
                    [],
                )

                record.outputs = metadata.get(
                    "outputs",
                    [],
                )

                updated += 1

                if updated % 100 == 0:
                    session.commit()

            except Exception:
                failed += 1

                logger.exception(
                    "Failed to backfill I/O for %s",
                    record.source_identifier,
                )

        session.commit()

    logger.info(
        "I/O backfill complete: %d updated, %d skipped, %d failed",
        updated,
        skipped,
        failed,
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    backfill_inputs_outputs()
