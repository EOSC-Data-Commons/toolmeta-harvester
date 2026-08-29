from __future__ import annotations

import logging
import requests
from pathlib import Path
from datetime import datetime
from urllib.parse import parse_qs, urlparse

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from toolmeta_harvester.db.engine import engine
from toolmeta_harvester.db.models import (
    Base,
    ToolMetadata,
    HarvestResult,
)
from toolmeta_harvester.extractors.extract_ro_crate_metadata import (
    extract_ro_crate_metadata,
)
from toolmeta_harvester.quality.metadata_quality import (
    assess_metadata_quality,
)
from toolmeta_harvester.tasks.workflowhub_rocrate import (
    WORKFLOW_HUB_API,
    download_rocrate,
    get_hub_workflows,
    get_latest_workflow_version_id,
    get_rocrate_url,
)
from toolmeta_harvester.flows.decorators import dynamic_harvest, static_harvest


PIPELINE_VERSION = "0.1.0"

PIPELINE_TAG = (
    f"{__name__.rsplit('.', 1)[-1].removeprefix('harvest_')}@{PIPELINE_VERSION}"
)


LOG_FILE = Path("logs/harvest_workflowhub.log")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s: %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler(LOG_FILE)],
)

logger = logging.getLogger(__name__)


def parse_datetime(value):
    """
    Convert metadata date strings to datetime.

    Returns None for missing or invalid values rather than
    failing the complete harvest.
    """

    if not value:
        return None

    if isinstance(value, datetime):
        return value

    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        logger.warning(
            "Unable to parse datetime: %r",
            value,
        )
        return None


def upsert_tool_metadata(
    session: Session,
    record: ToolMetadata,
) -> None:
    """
    Insert a new source record or replace its harvested metadata
    when the WorkflowHub version has changed.

    Database identity:
        source_url + source_identifier
    """

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


def create_tool_metadata(
    workflow: dict,
    crate: dict,
    pipeline_tag: str = PIPELINE_TAG,
) -> ToolMetadata:
    """
    Convert a WorkflowHub RO-Crate into the canonical
    ToolMetadata database representation.
    """

    metadata = extract_ro_crate_metadata(crate)

    quality = assess_metadata_quality(metadata)

    version = get_latest_workflow_version_id(workflow)

    metadata_url = get_rocrate_url(workflow)

    return ToolMetadata(
        quality_score=quality.score,
        # ---------------------------------------------------------
        # Provenance
        # ---------------------------------------------------------
        pipeline_tag=pipeline_tag,
        source_identifier=str(workflow.get("id"))
        if workflow.get("id") is not None
        else None,
        source_url=workflow.get("url"),
        metadata_url=metadata_url,
        metadata_format="ro-crate",
        metadata_version=metadata.get("metadata_version"),
        # ---------------------------------------------------------
        # CodeMeta / schema.org core
        # ---------------------------------------------------------
        title=metadata.get("title"),
        description=metadata.get("description"),
        raw_description=metadata.get("raw_description"),
        version=version,
        # version=(metadata.get("version") or (version.get("name") if version else None)),
        license=metadata.get("license"),
        identifiers=metadata.get(
            "identifiers",
            [],
        ),
        url=(metadata.get("url") or workflow.get("url")),
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
        # ---------------------------------------------------------
        # CodeMeta scientific extensions
        # ---------------------------------------------------------
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
        # ---------------------------------------------------------
        # Dates
        # ---------------------------------------------------------
        date_created=parse_datetime(metadata.get("date_created")),
        date_published=parse_datetime(metadata.get("date_published")),
        date_modified=parse_datetime(metadata.get("date_modified")),
        # ---------------------------------------------------------
        # Original metadata
        # ---------------------------------------------------------
        raw_metadata=crate,
    )


def get_harvested_versions(
    session: Session,
) -> dict[tuple[str, str], str]:
    rows = session.execute(
        select(
            ToolMetadata.source_url,
            ToolMetadata.source_identifier,
            ToolMetadata.version,
        ).where(ToolMetadata.metadata_format == "ro-crate")
    )

    return {
        (
            str(source_url).strip(),
            str(source_identifier).strip(),
        ): str(version).strip()
        for source_url, source_identifier, version in rows
        if source_url is not None
        and source_identifier is not None
        and version is not None
    }


# def get_harvested_versions(
#     session: Session,
# ) -> set[tuple[str, str]]:
#     rows = session.execute(
#         select(
#             ToolMetadata.source_identifier,
#             ToolMetadata.version,
#         ).where(ToolMetadata.metadata_format == "ro-crate")
#     )
#
#     return {
#         (str(source_id), str(version))
#         for source_id, version in rows
#         if source_id is not None and version is not None
#     }
#
def harvest_workflow(
    session: Session,
    workflow: dict,
    harvested: dict[tuple[str, str], str] | None = None,
) -> bool:
    """
    Harvest one WorkflowHub workflow.

    Returns True when a record was inserted or updated.
    Returns False when the current version was already harvested.
    """

    workflow_id = str(workflow.get("id")).strip()

    source_url = str(workflow.get("url")).strip()

    version = get_latest_workflow_version_id(workflow)

    if version is None:
        logger.warning(
            "Workflow %s has no versions",
            workflow_id,
        )
        return False

    version = str(version).strip()

    key = (
        source_url,
        workflow_id,
    )

    if harvested is not None:
        existing_version = harvested.get(key)

        if existing_version == version:
            logger.info(
                "Skipping WorkflowHub workflow %s version %s: already current",
                workflow_id,
                version,
            )
            return False

        if existing_version is None:
            logger.info(
                "Harvesting new WorkflowHub workflow %s version %s",
                workflow_id,
                version,
            )
        else:
            logger.info(
                "Updating WorkflowHub workflow %s from version %s to %s",
                workflow_id,
                existing_version,
                version,
            )

    crate = download_rocrate(workflow)

    tool_metadata = create_tool_metadata(
        workflow=workflow,
        crate=crate,
        pipeline_tag=PIPELINE_TAG,
    )

    upsert_tool_metadata(
        session,
        tool_metadata,
    )

    session.commit()

    if harvested is not None:
        harvested[key] = version

    logger.info(
        "Stored metadata for WorkflowHub workflow %s: %s",
        workflow_id,
        tool_metadata.title,
    )

    return True


def parse_workflowhub_url(
    url: str,
) -> tuple[str, str | None]:
    parsed = urlparse(url)

    parts = [part for part in parsed.path.split("/") if part]

    try:
        workflows_index = parts.index("workflows")
        workflow_id = parts[workflows_index + 1]
    except (ValueError, IndexError):
        raise ValueError(f"Invalid WorkflowHub workflow URL: {url}")

    query = parse_qs(parsed.query)

    requested_version = query.get(
        "version",
        [None],
    )[0]

    return workflow_id, requested_version


def get_workflow(
    workflow_id: str,
) -> dict:
    url = f"{WORKFLOW_HUB_API}/tools/{workflow_id}"

    response = requests.get(
        url,
        timeout=30,
        headers={
            "Accept": "application/json",
        },
    )

    response.raise_for_status()

    return response.json()


@dynamic_harvest(
    name="workflowhub",
    hosts=["workflowhub.eu"],
    default_schedule="0 3 * * *",
)
def pipeline_harvest_workflowhub_url(
    workflow_url: str,
) -> HarvestResult:
    Base.metadata.create_all(engine)

    workflow_id, requested_version = parse_workflowhub_url(workflow_url)

    workflow = get_workflow(workflow_id)

    # If a specific version was requested, make that version
    # appear as the latest version used by the existing helper
    # functions.
    if requested_version is not None:
        versions = workflow.get(
            "versions",
            [],
        )

        matching = [
            version
            for version in versions
            if str(version.get("id")) == str(requested_version)
            or str(version.get("name")) == str(requested_version)
        ]

        if not matching:
            raise ValueError(
                f"Workflow {workflow_id} has no version {requested_version}"
            )

        workflow = dict(workflow)
        workflow["versions"] = matching

    with Session(
        engine,
        expire_on_commit=False,
    ) as session:
        harvested = get_harvested_versions(session)

        try:
            changed = harvest_workflow(
                session=session,
                workflow=workflow,
                harvested=harvested,
            )

            if changed:
                return HarvestResult(
                    pipeline_tag=PIPELINE_TAG,
                    record_ids=[workflow_id],
                    failed_record_ids=[],
                )
            else:
                return HarvestResult(
                    pipeline_tag=PIPELINE_TAG,
                    record_ids=[],
                    failed_record_ids=[],
                )

        except Exception:
            session.rollback()
            raise


@static_harvest(
    name="workflowhub_all",
    default_schedule="0 3 * * *",
)
def pipeline_harvest_workflowhub(
    limit: int | None = None,
    use_cache: bool = True,
) -> HarvestResult:
    """
    Harvest WorkflowHub RO-Crates and persist their normalised
    metadata in PostgreSQL.
    """

    Base.metadata.create_all(engine)

    workflows = get_hub_workflows(use_cache=use_cache)

    if limit is not None:
        workflows = workflows[:limit]

    record_ids = []
    failed_record_ids = []

    with Session(
        engine,
        expire_on_commit=False,
    ) as session:
        harvested = get_harvested_versions(session)
        try:
            for workflow in workflows:
                try:
                    changed = harvest_workflow(
                        session=session,
                        workflow=workflow,
                        harvested=harvested,
                    )

                    if changed:
                        record_ids.append(str(workflow.get("id")))

                except Exception:
                    session.rollback()
                    failed_record_ids.append(str(workflow.get("id")))
                    logger.exception(
                        "Failed to harvest WorkflowHub workflow %s",
                        workflow.get("id"),
                    )

            return HarvestResult(
                pipeline_tag=PIPELINE_TAG,
                record_ids=record_ids,
                failed_record_ids=failed_record_ids,
            )

        except Exception as exc:
            session.rollback()
            raise exc


def main():
    import argparse

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "url",
        nargs="?",
        help=("Optional WorkflowHub workflow URL. If omitted, harvest all workflows."),
    )

    parser.add_argument(
        "--limit",
        type=int,
    )

    parser.add_argument(
        "--no-cache",
        action="store_true",
    )

    args = parser.parse_args()

    if args.url:
        pipeline_harvest_workflowhub_url(args.url)
    else:
        pipeline_harvest_workflowhub(
            limit=args.limit,
            use_cache=not args.no_cache,
        )


if __name__ == "__main__":
    main()
