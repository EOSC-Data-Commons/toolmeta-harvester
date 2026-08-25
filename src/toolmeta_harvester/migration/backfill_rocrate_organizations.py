from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from toolmeta_harvester.db.engine import engine
from toolmeta_harvester.db.models import ToolMetadata
from toolmeta_harvester.extractors.extract_ro_crate_metadata import (
    build_entity_index,
    get_main_entity,
    get_root_entity,
    extract_organizations,
)

logger = logging.getLogger(__name__)


def backfill_organizations() -> None:
    updated = 0
    skipped = 0
    failed = 0

    with Session(engine) as session:
        records = session.scalars(
            select(ToolMetadata).where(ToolMetadata.metadata_format == "ro-crate")
        )

        for record in records:
            try:
                crate = record.raw_metadata

                if not crate:
                    skipped += 1
                    continue

                entities = build_entity_index(crate)
                root = get_root_entity(crate, entities)
                main = get_main_entity(root, entities) or root

                organizations = extract_organizations(
                    main=main,
                    root=root,
                    entities=entities,
                )

                record.organizations = organizations

                updated += 1

                if updated % 100 == 0:
                    session.commit()
                    logger.info(
                        "Updated %d records",
                        updated,
                    )

            except Exception:
                failed += 1

                logger.exception(
                    "Failed to extract organizations for record %s",
                    record.id,
                )

        session.commit()

    logger.info(
        "Organization backfill complete: %d updated, %d skipped, %d failed",
        updated,
        skipped,
        failed,
    )


if __name__ == "__main__":
    backfill_organizations()
