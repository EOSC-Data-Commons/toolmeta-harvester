from __future__ import annotations

import argparse
import logging
from datetime import datetime

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
from toolmeta_harvester.extractors.tool_metadata import extract_tool_metadata
from toolmeta_harvester.flows.decorators import static_harvest
from toolmeta_harvester.quality.metadata_quality import assess_metadata_quality


RSD_BASE_URL = "https://research-software-directory.org"
RSD_API_URL = f"{RSD_BASE_URL}/api/v1"
RSD_CODEMETA_URL = f"{RSD_BASE_URL}/metadata/codemeta/v3"

PIPELINE_VERSION = "0.1.0"

PIPELINE_TAG = (
    f"{__name__.rsplit('.', 1)[-1].removeprefix('harvest_')}@{PIPELINE_VERSION}"
)

logger = logging.getLogger(__name__)


def parse_datetime(value):
    if not value:
        return None

    if isinstance(value, datetime):
        return value

    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        logger.warning("Unable to parse datetime %r", value)
        return None


def _canonical_version(metadata: dict) -> str | None:
    value = metadata.get("version")

    if value is None:
        return None

    if isinstance(value, list):
        return ", ".join(str(v) for v in value)

    return str(value)


def get_rsd_software(
    *,
    limit: int | None = None,
) -> list[dict]:
    """
    Retrieve public RSD software records.

    Only fields needed for discovering CodeMeta records are requested.
    """

    params = {
        "select": "id,slug,brand_name",
        "order": "slug.asc",
    }

    if limit is not None:
        params["limit"] = str(limit)

    response = requests.get(
        f"{RSD_API_URL}/software",
        params=params,
        headers={
            "Accept": "application/json",
        },
        timeout=60,
    )

    response.raise_for_status()

    return response.json()


def get_codemeta_url(slug: str) -> str:
    return f"{RSD_CODEMETA_URL}/{slug}/"


def get_codemeta(slug: str) -> dict:
    url = get_codemeta_url(slug)

    response = requests.get(
        url,
        headers={
            "Accept": "application/ld+json, application/json",
        },
        timeout=60,
    )

    response.raise_for_status()

    return response.json()


def create_tool_metadata(
    *,
    software: dict,
    codemeta: dict,
    pipeline_tag: str = PIPELINE_TAG,
) -> ToolMetadata:
    """
    Convert RSD CodeMeta into ToolMetadata using the common
    CodeMeta/schema.org extractor.
    """

    metadata = extract_tool_metadata(codemeta)
    quality = assess_metadata_quality(metadata)

    slug = software["slug"]

    source_url = f"{RSD_BASE_URL}/software/{slug}"
    metadata_url = get_codemeta_url(slug)

    return ToolMetadata(
        quality_score=quality.score,
        # ---------------------------------------------------------
        # Provenance
        # ---------------------------------------------------------
        pipeline_tag=pipeline_tag,
        source_identifier=str(software.get("id") or slug),
        source_url=source_url,
        metadata_url=metadata_url,
        metadata_format="codemeta",
        metadata_version=metadata.get("metadata_version"),
        # ---------------------------------------------------------
        # CodeMeta / schema.org core
        # ---------------------------------------------------------
        title=metadata.get("title"),
        description=metadata.get("description"),
        raw_description=metadata.get("raw_description"),
        version=_canonical_version(metadata),
        license=metadata.get("license"),
        identifiers=metadata.get("identifiers", []),
        url=metadata.get("url") or source_url,
        code_repository=metadata.get("code_repository"),
        keywords=metadata.get("keywords", []),
        authors=metadata.get("authors", []),
        organizations=metadata.get("organizations", []),
        types=metadata.get("types", []),
        programming_languages=metadata.get("programming_languages", []),
        runtime_platforms=metadata.get("runtime_platforms", []),
        software_requirements=metadata.get("software_requirements", []),
        # ---------------------------------------------------------
        # Scientific extensions
        # ---------------------------------------------------------
        software_types=metadata.get("software_types", []),
        consumes_data=metadata.get("consumes_data", []),
        produces_data=metadata.get("produces_data", []),
        # ---------------------------------------------------------
        # RO-Crate inputs / outputs
        # ---------------------------------------------------------
        inputs=metadata.get("inputs", []),
        outputs=metadata.get("outputs", []),
        # ---------------------------------------------------------
        # Dates
        # ---------------------------------------------------------
        date_created=parse_datetime(metadata.get("date_created")),
        date_published=parse_datetime(metadata.get("date_published")),
        date_modified=parse_datetime(metadata.get("date_modified")),
        # ---------------------------------------------------------
        # Original metadata
        # ---------------------------------------------------------
        raw_metadata=codemeta,
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
        column.name: getattr(record, column.name)
        for column in ToolMetadata.__table__.columns
        if column.name not in excluded_from_insert
    }

    stmt = insert(ToolMetadata).values(**values)

    excluded = stmt.excluded

    excluded_from_update = {
        "id",
        "source_url",
        "source_identifier",
        "harvested_at",
    }

    update_values = {
        column.name: getattr(excluded, column.name)
        for column in ToolMetadata.__table__.columns
        if column.name not in excluded_from_update
    }

    update_values["harvested_at"] = func.now()

    stmt = stmt.on_conflict_do_update(
        constraint="uq_tool_metadata_source",
        set_=update_values,
    )

    session.execute(stmt)


def harvest_rsd_software(
    *,
    session: Session,
    software: dict,
) -> str:
    slug = software["slug"]

    logger.info("Harvesting RSD software %s", slug)

    codemeta = get_codemeta(slug)

    record = create_tool_metadata(
        software=software,
        codemeta=codemeta,
    )

    logger.info(
        "Record: %s",
        {
            column.name: getattr(record, column.name)
            for column in record.__table__.columns
        },
    )

    upsert_tool_metadata(
        session,
        record,
    )

    session.commit()

    logger.info(
        "Stored RSD software %s (quality=%.3f)",
        slug,
        record.quality_score,
    )

    return str(software.get("id") or slug)


def iter_rsd_software(
    *,
    page_size: int = 500,
    limit: int | None = None,
):
    offset = 0
    yielded = 0

    while True:
        request_limit = page_size

        if limit is not None:
            remaining = limit - yielded

            if remaining <= 0:
                return

            request_limit = min(request_limit, remaining)

        response = requests.get(
            f"{RSD_API_URL}/software",
            params={
                "select": "id,slug,brand_name",
                "order": "slug.asc",
                "limit": request_limit,
                "offset": offset,
            },
            headers={"Accept": "application/json"},
            timeout=60,
        )

        response.raise_for_status()

        records = response.json()

        if not records:
            return

        yield from records

        yielded += len(records)
        offset += len(records)

        if len(records) < request_limit:
            return


@static_harvest(
    name="rsd",
    default_schedule="0 3 * * *",
)
def pipeline_harvest_rsd(
    limit: int | None = None,
) -> HarvestResult:
    """
    Harvest software from the Research Software Directory.

    Software records are discovered using the RSD REST API.
    Metadata is retrieved from each record's CodeMeta endpoint and
    normalized using the common CodeMeta extractor.
    """

    Base.metadata.create_all(engine)

    # software_records = get_rsd_software(limit=limit)

    record_ids: list[str] = []
    failed_record_ids: list[str] = []

    with Session(
        engine,
        expire_on_commit=False,
    ) as session:
        # for software in software_records:
        for software in iter_rsd_software(limit=limit):
            slug = str(software.get("slug"))

            try:
                record_id = harvest_rsd_software(
                    session=session,
                    software=software,
                )

                record_ids.append(record_id)

            except Exception:
                session.rollback()

                failed_record_ids.append(str(software.get("id") or slug))

                logger.exception(
                    "Failed to harvest RSD software %s",
                    slug,
                )

    return HarvestResult(
        pipeline_tag=PIPELINE_TAG,
        record_ids=record_ids,
        failed_record_ids=failed_record_ids,
    )


def main():
    parser = argparse.ArgumentParser(
        description="Harvest software from the Research Software Directory"
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=None,
    )

    args = parser.parse_args()

    pipeline_harvest_rsd(
        limit=args.limit,
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
