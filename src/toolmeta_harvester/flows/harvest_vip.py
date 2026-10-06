from __future__ import annotations

import argparse
import logging
from pathlib import Path

import requests
from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from toolmeta_harvester.db.engine import engine
from toolmeta_harvester.db.models import (
    Base,
    HarvestResult,
    ToolMetadata,
)
from toolmeta_harvester.extractors.boutiques import (
    extract_boutiques_metadata,
)
from toolmeta_harvester.flows.decorators import static_harvest
from toolmeta_harvester.quality.metadata_quality import (
    assess_metadata_quality,
)


VIP_API = "https://vip.creatis.insa-lyon.fr/rest/pipelines"
TEST_VIP_API = (
    "https://vip.creatis.insa-lyon.fr/test/rest/pipelines?public&format=boutiques"
)


PIPELINE_VERSION = "0.1.0"
PIPELINE_TAG = f"vip@{PIPELINE_VERSION}"

LOG_FILE = Path("logs/harvest_vip.log")

logger = logging.getLogger(__name__)


def get_vip_pipelines() -> list[dict]:
    """
    Fetch all public VIP pipelines as Boutiques descriptors.
    """
    response = requests.get(
        TEST_VIP_API,
        headers={
            "Accept": "application/json",
        },
        timeout=60,
    )
    response.raise_for_status()

    data = response.json()

    if not isinstance(data, list):
        raise ValueError(
            f"Expected VIP API to return a list, got {type(data).__name__}"
        )

    return data


def get_source_identifier(
    descriptor: dict,
) -> str:
    """
    VIP's Boutiques endpoint does not expose a separate persistent ID.

    Name + version distinguishes descriptors when VIP exposes multiple
    versions of the same tool simultaneously.
    """
    name = descriptor.get("name")
    version = descriptor.get("tool-version")

    if not name:
        raise ValueError("Boutiques descriptor has no name")

    if version:
        return f"{name}/{version}"

    return name


def create_tool_metadata(
    descriptor: dict,
    *,
    pipeline_tag: str = PIPELINE_TAG,
) -> ToolMetadata:
    metadata = extract_boutiques_metadata(descriptor)

    quality = assess_metadata_quality(metadata)

    return ToolMetadata(
        quality_score=quality.score,
        # Provenance
        pipeline_tag=pipeline_tag,
        source_identifier=get_source_identifier(descriptor),
        source_url=f"{VIP_API}/{get_source_identifier(descriptor)}",
        metadata_url=VIP_API,
        metadata_format="boutiques",
        metadata_version=descriptor.get("schema-version"),
        # Canonical metadata
        title=metadata.get("title"),
        description=metadata.get("description"),
        raw_description=metadata.get("raw_description"),
        version=metadata.get("version"),
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
        # Scientific metadata
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
        # Dates
        date_created=metadata.get("date_created"),
        date_published=metadata.get("date_published"),
        date_modified=metadata.get("date_modified"),
        # Keep complete Boutiques descriptor
        raw_metadata=descriptor,
    )


def upsert_tool_metadata(
    session: Session,
    record: ToolMetadata,
) -> None:
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

    update_values["harvested_at"] = func.now()

    stmt = stmt.on_conflict_do_update(
        constraint="uq_tool_metadata_source",
        set_=update_values,
    )

    session.execute(stmt)


def harvest_pipeline(
    session: Session,
    descriptor: dict,
) -> bool:
    source_identifier = get_source_identifier(descriptor)

    tool_metadata = create_tool_metadata(descriptor)

    upsert_tool_metadata(
        session,
        tool_metadata,
    )

    session.commit()

    logger.info(
        "Stored VIP pipeline %s: %s",
        source_identifier,
        tool_metadata.title,
    )

    return True


@static_harvest(
    name="vip",
    default_schedule="0 22 * * 6",
)
def pipeline_harvest_vip(
    limit: int | None = None,
) -> HarvestResult:
    Base.metadata.create_all(engine)

    descriptors = get_vip_pipelines()

    if limit is not None:
        descriptors = descriptors[:limit]

    record_ids: list[str] = []
    failed_record_ids: list[str] = []

    with Session(
        engine,
        expire_on_commit=False,
    ) as session:
        for descriptor in descriptors:
            try:
                source_identifier = get_source_identifier(descriptor)

                harvest_pipeline(
                    session,
                    descriptor,
                )

                record_ids.append(source_identifier)

            except Exception:
                session.rollback()

                source_identifier = descriptor.get("name") or "unknown"

                failed_record_ids.append(source_identifier)

                logger.exception(
                    "Failed to harvest VIP pipeline %s",
                    source_identifier,
                )

    return HarvestResult(
        pipeline_tag=PIPELINE_TAG,
        record_ids=record_ids,
        failed_record_ids=failed_record_ids,
    )


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--limit",
        type=int,
        default=None,
    )

    args = parser.parse_args()

    result = pipeline_harvest_vip(limit=args.limit)

    logger.info(
        "Harvest complete: %d stored, %d failed",
        len(result.record_ids),
        len(result.failed_record_ids),
    )


if __name__ == "__main__":
    main()
