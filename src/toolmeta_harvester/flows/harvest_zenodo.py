from __future__ import annotations

import argparse
import logging
from datetime import datetime
from pathlib import Path

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from toolmeta_harvester.db.engine import engine
from toolmeta_harvester.db.models import (
    Base,
    ToolHarvestRun,
    ToolMetadata,
)
from toolmeta_harvester.extractors.extract_ro_crate_metadata import (
    extract_ro_crate_metadata,
    ro_crate_defines_tool,
)
from toolmeta_harvester.quality.metadata_quality import (
    assess_metadata_quality,
)
from toolmeta_harvester.tasks.zenodo_jsonld import (
    download_zenodo_jsonld,
    get_zenodo_record,
    parse_zenodo_url,
)


LOG_FILE = Path("logs/harvest_zenodo.log")

LOG_FILE.parent.mkdir(
    parents=True,
    exist_ok=True,
)

logging.basicConfig(
    level=logging.INFO,
    format=("%(asctime)s %(name)s %(levelname)s: %(message)s"),
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_FILE),
    ],
)

logger = logging.getLogger(__name__)


def upsert_tool_metadata(
    session: Session,
    record: ToolMetadata,
) -> None:
    values = {
        column.name: getattr(
            record,
            column.name,
        )
        for column in ToolMetadata.__table__.columns
        if column.name != "id"
    }

    stmt = insert(ToolMetadata).values(**values)

    excluded = stmt.excluded

    update_values = {
        column.name: getattr(
            excluded,
            column.name,
        )
        for column in ToolMetadata.__table__.columns
        if column.name
        not in {
            "id",
            "source_url",
            "source_identifier",
        }
    }

    stmt = stmt.on_conflict_do_update(
        constraint="uq_tool_metadata_source",
        set_=update_values,
    )

    session.execute(stmt)


def parse_datetime(value):
    if not value:
        return None

    if isinstance(value, datetime):
        return value

    try:
        return datetime.fromisoformat(
            str(value).replace(
                "Z",
                "+00:00",
            )
        )
    except (TypeError, ValueError):
        logger.warning(
            "Unable to parse datetime: %r",
            value,
        )

        return None


def get_zenodo_source_url(
    record_id: str,
) -> str:
    return f"https://zenodo.org/records/{record_id}"


def create_tool_metadata(
    record: dict,
    crate: dict,
    metadata_url: str,
    harvest_run_id,
) -> ToolMetadata:
    metadata = extract_ro_crate_metadata(crate)

    quality = assess_metadata_quality(metadata)

    record_id = str(record.get("id"))

    source_url = get_zenodo_source_url(record_id)

    return ToolMetadata(
        harvest_run_id=harvest_run_id,
        quality_score=quality.score,
        # -----------------------------------------------------
        # Provenance
        # -----------------------------------------------------
        source_identifier=record_id,
        source_url=source_url,
        metadata_url=metadata_url,
        metadata_format="ro-crate",
        metadata_version=metadata.get("metadata_version"),
        # -----------------------------------------------------
        # CodeMeta / schema.org
        # -----------------------------------------------------
        title=metadata.get("title"),
        description=metadata.get("description"),
        raw_description=metadata.get("raw_description"),
        version=(
            str(metadata["version"]) if metadata.get("version") is not None else None
        ),
        license=metadata.get("license"),
        identifiers=metadata.get(
            "identifiers",
            [],
        ),
        url=(metadata.get("url") or source_url),
        code_repository=metadata.get("code_repository"),
        keywords=metadata.get(
            "keywords",
            [],
        ),
        authors=metadata.get(
            "authors",
            [],
        ),
        organizations=metadata.get(
            "organizations",
            [],
        ),
        types=metadata.get(
            "types",
            [],
        ),
        programming_languages=metadata.get(
            "programming_languages",
            [],
        ),
        runtime_platforms=metadata.get(
            "runtime_platforms",
            [],
        ),
        software_requirements=metadata.get(
            "software_requirements",
            [],
        ),
        # -----------------------------------------------------
        # CodeMeta scientific extensions
        # -----------------------------------------------------
        software_types=metadata.get(
            "software_types",
            [],
        ),
        consumes_data=metadata.get(
            "consumes_data",
            [],
        ),
        produces_data=metadata.get(
            "produces_data",
            [],
        ),
        inputs=metadata.get(
            "inputs",
            [],
        ),
        outputs=metadata.get(
            "outputs",
            [],
        ),
        # -----------------------------------------------------
        # Dates
        # -----------------------------------------------------
        date_created=parse_datetime(metadata.get("date_created")),
        date_published=parse_datetime(metadata.get("date_published")),
        date_modified=parse_datetime(metadata.get("date_modified")),
        raw_metadata=crate,
    )


def pipeline_harvest_zenodo(
    zenodo_url: str,
) -> ToolHarvestRun:
    """
    Harvest an RO-Crate from one Zenodo record.

    The record is only accepted when the RO-Crate's primary
    entity defines a software tool/workflow.
    """

    Base.metadata.create_all(engine)

    record_id = parse_zenodo_url(zenodo_url)

    record = get_zenodo_record(record_id)

    with Session(engine) as session:
        harvest_run = ToolHarvestRun(
            source="zenodo",
            source_url="https://zenodo.org",
            status="running",
        )

        session.add(harvest_run)
        session.commit()
        session.refresh(harvest_run)

        harvest_run_id = harvest_run.id

        try:
            logger.info(
                "Retrieving RO-Crate from Zenodo record %s",
                record_id,
            )

            crate, metadata_url = download_zenodo_jsonld(record)

            # -------------------------------------------------
            # Tool acceptance gate
            # -------------------------------------------------

            if not ro_crate_defines_tool(crate):
                logger.warning(
                    "Rejecting Zenodo record %s: RO-Crate does not define a tool",
                    record_id,
                )

                harvest_run = session.get(
                    ToolHarvestRun,
                    harvest_run_id,
                )

                harvest_run.harvested_count = 0
                harvest_run.failed_count = 0
                harvest_run.status = "completed"
                harvest_run.finished_at = datetime.now().astimezone()

                session.commit()

                return harvest_run

            # -------------------------------------------------
            # Normal extraction
            # -------------------------------------------------

            tool_metadata = create_tool_metadata(
                record=record,
                crate=crate,
                metadata_url=metadata_url,
                harvest_run_id=(harvest_run_id),
            )

            upsert_tool_metadata(
                session,
                tool_metadata,
            )

            harvest_run = session.get(
                ToolHarvestRun,
                harvest_run_id,
            )

            harvest_run.harvested_count = 1
            harvest_run.failed_count = 0
            harvest_run.status = "completed"
            harvest_run.finished_at = datetime.now().astimezone()

            session.commit()

            logger.info(
                "Stored Zenodo tool %s: %s (quality %.3f)",
                record_id,
                tool_metadata.title,
                tool_metadata.quality_score,
            )

            return harvest_run

        except Exception:
            session.rollback()

            harvest_run = session.get(
                ToolHarvestRun,
                harvest_run_id,
            )

            harvest_run.harvested_count = 0
            harvest_run.failed_count = 1
            harvest_run.status = "failed"
            harvest_run.finished_at = datetime.now().astimezone()

            session.commit()

            logger.exception(
                "Failed to harvest Zenodo record %s",
                record_id,
            )

            raise


def main():
    parser = argparse.ArgumentParser(
        description=("Harvest a tool RO-Crate from a Zenodo record")
    )

    parser.add_argument(
        "url",
        help=("Zenodo record URL, e.g. https://zenodo.org/records/123456"),
    )

    args = parser.parse_args()

    pipeline_harvest_zenodo(args.url)


if __name__ == "__main__":
    main()
