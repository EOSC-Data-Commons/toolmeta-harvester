from __future__ import annotations

import argparse
import logging
from datetime import datetime
from sqlalchemy import func

from sqlalchemy.dialects.postgresql import (
    insert,
)
from sqlalchemy.orm import Session

from toolmeta_harvester.converters.biotools_jsonld import (
    convert_biotools_to_jsonld,
)
from toolmeta_harvester.db.engine import (
    engine,
)
from toolmeta_harvester.db.models import (
    Base,
    ToolMetadata,
    HarvestResult,
)
from toolmeta_harvester.extractors.tool_metadata import (
    extract_tool_metadata,
)
from toolmeta_harvester.quality.metadata_quality import (
    assess_metadata_quality,
)
from toolmeta_harvester.tasks.biotools_bioschemas import (
    get_biotools_id,
    get_biotools_metadata_url,
    get_biotools_record,
    get_biotools_source_url,
    iter_biotools,
)
from toolmeta_harvester.flows.decorators import dynamic_harvest, static_harvest

PIPELINE_VERSION = "0.1.0"

PIPELINE_TAG = (
    f"{__name__.rsplit('.', 1)[-1].removeprefix('harvest_')}@{PIPELINE_VERSION}"
)


logger = logging.getLogger(__name__)


def parse_datetime(
    value,
):
    if not value:
        return None

    if isinstance(
        value,
        datetime,
    ):
        return value

    try:
        return datetime.fromisoformat(
            str(value).replace(
                "Z",
                "+00:00",
            )
        )

    except (
        TypeError,
        ValueError,
    ):
        logger.warning(
            "Unable to parse datetime %r",
            value,
        )

        return None


def create_tool_metadata(
    biotools_id: str,
    raw_biotools: dict,
    metadata: dict,
    pipeline_tag: str = PIPELINE_TAG,
) -> ToolMetadata:
    """
    Convert canonical ScienceToolMeta into the SQLAlchemy model.

    raw_metadata deliberately stores the original biotoolsSchema
    record rather than the internally generated JSON-LD.
    """

    quality = assess_metadata_quality(metadata)

    version = metadata.get("version")

    if version is not None:
        version = str(version)

    return ToolMetadata(
        quality_score=(quality.score),
        # -----------------------------------------------------
        # Provenance
        # -----------------------------------------------------
        pipeline_tag=(pipeline_tag),
        source_identifier=(biotools_id),
        source_url=(get_biotools_source_url(biotools_id)),
        metadata_url=(get_biotools_metadata_url(biotools_id)),
        # Important: this is the harvested source format,
        # not the internal intermediary format.
        metadata_format=("biotoolsSchema"),
        metadata_version=("3.3.0"),
        # -----------------------------------------------------
        # Canonical metadata
        # -----------------------------------------------------
        title=metadata.get("title"),
        description=metadata.get("description"),
        raw_description=metadata.get("raw_description"),
        version=version,
        license=metadata.get("license"),
        identifiers=metadata.get(
            "identifiers",
            [],
        ),
        url=metadata.get("url"),
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
        programming_languages=(
            metadata.get(
                "programming_languages",
                [],
            )
        ),
        runtime_platforms=(
            metadata.get(
                "runtime_platforms",
                [],
            )
        ),
        software_requirements=(
            metadata.get(
                "software_requirements",
                [],
            )
        ),
        # -----------------------------------------------------
        # Scientific extensions
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
        # Preserve the actual harvested representation.
        raw_metadata=raw_biotools,
    )


def upsert_tool_metadata(
    session: Session,
    record: ToolMetadata,
) -> None:
    """
    Insert or update the logical source record.

    Identity:
        source_url + source_identifier
    """

    excluded_from_insert = {
        "id",
        "harvested_at",
    }

    values = {
        column.name: getattr(
            record,
            column.name,
        )
        for column in ToolMetadata.__table__.columns
        if column.name not in excluded_from_insert
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
            "harvested_at",
        }
    }

    # A re-harvest should refresh the timestamp.
    update_values["harvested_at"] = func.now()

    stmt = stmt.on_conflict_do_update(
        constraint=("uq_tool_metadata_source"),
        set_=update_values,
    )

    session.execute(stmt)


def get_biotools_id_from_url(url: str) -> str:
    """
    Extract the bio.tools ID from a URL.
    """

    if not url.startswith("https://bio.tools/"):
        raise ValueError(
            f"Invalid bio.tools URL: {url}",
        )

    return url.split("/")[-1]


@dynamic_harvest(
    name="biotools",
    default_schedule="0 3 * * *",
)
def pipeline_harvest_biotools_url(
    url: str,
) -> ToolMetadata:
    """
    Run the complete pipeline for one bio.tools record.
    """

    biotools_id = get_biotools_id_from_url(url)

    return harvest_biotools_record(
        session=Session(engine),
        biotools_id=(biotools_id),
    )


def harvest_biotools_record(
    session: Session,
    biotools_id: str,
) -> ToolMetadata:
    """
    Run the complete pipeline for one bio.tools record.
    """

    # 1. Harvest native biotoolsSchema JSON
    raw_biotools = get_biotools_record(biotools_id)

    # 2. Crosswalk to JSON-LD
    jsonld = convert_biotools_to_jsonld(raw_biotools)

    # 3. Generic extraction into ScienceToolMeta
    metadata = extract_tool_metadata(jsonld)

    # 4. DB model + quality
    tool_metadata = create_tool_metadata(
        biotools_id=(biotools_id),
        raw_biotools=(raw_biotools),
        metadata=metadata,
        pipeline_tag=(PIPELINE_TAG),
    )

    # 5. Persistent upsert
    upsert_tool_metadata(
        session,
        tool_metadata,
    )

    return tool_metadata


@static_harvest(
    name="biotools_all",
    default_schedule="0 3 * * *",
)
def pipeline_harvest_biotools(
    limit: int | None = None,
    per_page: int = 50,
) -> HarvestResult:
    Base.metadata.create_all(engine)

    record_ids = []
    failed_ids = []

    with Session(
        engine,
        expire_on_commit=False,
    ) as session:
        try:
            for summary in iter_biotools(
                limit=limit,
                per_page=per_page,
            ):
                biotools_id = None

                try:
                    biotools_id = get_biotools_id(summary)

                    logger.info(
                        "Harvesting bio.tools record %s",
                        biotools_id,
                    )

                    record = harvest_biotools_record(
                        session=session,
                        biotools_id=(biotools_id),
                        pipeline_tag=(PIPELINE_TAG),
                    )

                    session.commit()

                    record_ids.append(biotools_id)

                    logger.info(
                        "Stored bio.tools record %s: %s",
                        biotools_id,
                        record.title,
                    )

                except Exception:
                    session.rollback()

                    failed_ids.append(biotools_id)

                    logger.exception(
                        "Failed to harvest bio.tools record %s",
                        biotools_id,
                    )

            logger.info(
                "bio.tools harvest complete: %d harvested, %d failed",
                len(record_ids),
                len(failed_ids),
            )

            return HarvestResult(
                pipeline_tag=PIPELINE_TAG,
                record_ids=record_ids,
                failed_record_ids=failed_ids,
            )

        except Exception:
            session.rollback()
            raise


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Harvest bio.tools metadata "
            "through the biotoolsSchema "
            "→ JSON-LD → ScienceToolMeta pipeline"
        )
    )

    parser.add_argument(
        "--limit",
        type=int,
    )

    parser.add_argument(
        "--per-page",
        type=int,
        default=50,
    )

    args = parser.parse_args()

    pipeline_harvest_biotools(
        limit=args.limit,
        per_page=args.per_page,
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    main()
