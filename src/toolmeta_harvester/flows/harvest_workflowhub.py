from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import requests
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from toolmeta_harvester.db.engine import engine
from toolmeta_harvester.db.models import (
    Base,
    HarvestResult,
    ToolMetadata,
)
from toolmeta_harvester.extractors.workflowhub_json import (
    extract_workflowhub_metadata,
)
from toolmeta_harvester.flows.decorators import (
    dynamic_harvest,
    static_harvest,
)
from toolmeta_harvester.quality.metadata_quality import (
    assess_metadata_quality,
)
from toolmeta_harvester.tasks.workflowhub_rocrate import (
    get_hub_workflows,
    get_latest_workflow_version_id,
)


WORKFLOW_HUB_URL = "https://workflowhub.eu"

PIPELINE_VERSION = "0.2.0"

PIPELINE_TAG = (
    f"{__name__.rsplit('.', 1)[-1].removeprefix('harvest_')}@{PIPELINE_VERSION}"
)


LOG_FILE = Path("logs/harvest_workflowhub.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_FILE),
    ],
)

logger = logging.getLogger(__name__)


def parse_datetime(
    value,
):
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


def get_workflow_json(
    workflow_id: str,
    version: str | int | None = None,
) -> dict:
    """
    Fetch WorkflowHub's JSON representation for a workflow.

    Example:

        https://workflowhub.org/workflows/401.json

    When a version is supplied:

        https://workflowhub.org/workflows/401.json?version=16
    """
    url = f"{WORKFLOW_HUB_URL}/workflows/{workflow_id}.json"

    params = {}

    if version is not None:
        params["version"] = str(version)

    response = requests.get(
        url,
        params=params,
        timeout=30,
        headers={
            "Accept": "application/vnd.api+json",
        },
    )

    response.raise_for_status()

    return response.json()


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
        constraint="uq_tool_metadata_source",
        set_=update_values,
    )

    session.execute(stmt)


def create_tool_metadata(
    workflow_json: dict,
    pipeline_tag: str = PIPELINE_TAG,
) -> ToolMetadata:
    """
    Convert WorkflowHub JSON API metadata into the canonical
    ToolMetadata database representation.
    """
    metadata = extract_workflowhub_metadata(workflow_json)

    quality = assess_metadata_quality(metadata)

    data = workflow_json.get("data") or {}
    attributes = data.get("attributes") or {}
    meta = data.get("meta") or {}

    workflow_id = data.get("id")

    if workflow_id is not None:
        workflow_id = str(workflow_id)

    source_url = f"{WORKFLOW_HUB_URL}/workflows/{workflow_id}" if workflow_id else None

    metadata_url = (
        f"{WORKFLOW_HUB_URL}/workflows/{workflow_id}.json" if workflow_id else None
    )

    version = metadata.get("version")

    if version is not None:
        version = str(version)

    return ToolMetadata(
        quality_score=quality.score,
        # ---------------------------------------------------------
        # Provenance
        # ---------------------------------------------------------
        pipeline_tag=pipeline_tag,
        source_identifier=workflow_id,
        source_url=source_url,
        metadata_url=metadata_url,
        metadata_format="workflowhub-json",
        metadata_version=(metadata.get("metadata_version") or meta.get("api_version")),
        # ---------------------------------------------------------
        # CodeMeta / schema.org core
        # ---------------------------------------------------------
        title=metadata.get("title"),
        description=metadata.get("description"),
        raw_description=metadata.get("raw_description"),
        version=version,
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
        # Original WorkflowHub JSON
        # ---------------------------------------------------------
        raw_metadata=workflow_json,
    )


def get_harvested_versions(
    session: Session,
) -> dict[tuple[str, str], str]:
    """
    Return:

        (source_url, source_identifier) -> version

    for WorkflowHub records already stored in the database.
    """
    rows = session.execute(
        select(
            ToolMetadata.source_url,
            ToolMetadata.source_identifier,
            ToolMetadata.version,
        ).where(ToolMetadata.metadata_format == "workflowhub-json")
    )

    return {
        (
            str(source_url).strip(),
            str(source_identifier).strip(),
        ): str(version).strip()
        for (
            source_url,
            source_identifier,
            version,
        ) in rows
        if source_url is not None
        and source_identifier is not None
        and version is not None
    }


def harvest_workflow(
    session: Session,
    workflow: dict,
    harvested: dict[tuple[str, str], str] | None = None,
    requested_version: str | int | None = None,
    force: bool = False,
) -> bool:
    """
    Harvest one WorkflowHub workflow.

    Returns True when a record was inserted or updated.

    Returns False when the current version was already harvested.
    """
    workflow_id = str(workflow.get("id")).strip()

    source_url = f"{WORKFLOW_HUB_URL}/workflows/{workflow_id}"

    if requested_version is not None:
        version = str(requested_version).strip()
    else:
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
            if not force:
                logger.info(
                    "Skipping WorkflowHub workflow %s version %s: already current",
                    workflow_id,
                    version,
                )
                return False

            logger.info(
                "Force re-harvesting WorkflowHub workflow %s version %s",
                workflow_id,
                version,
            )

        elif existing_version is None:
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

    workflow_json = get_workflow_json(
        workflow_id,
        version=requested_version,
    )

    tool_metadata = create_tool_metadata(
        workflow_json=workflow_json,
        pipeline_tag=PIPELINE_TAG,
    )

    #
    # Make sure the stored version corresponds to the version
    # selected by the harvesting logic.
    #
    # This is particularly important for explicit ?version=N
    # requests.
    #
    tool_metadata.version = version

    upsert_tool_metadata(
        session,
        tool_metadata,
    )

    session.commit()

    if harvested is not None:
        harvested[key] = version

    logger.info(
        "Stored metadata for WorkflowHub workflow %s version %s: %s",
        workflow_id,
        version,
        tool_metadata.title,
    )

    return True


def parse_workflowhub_url(
    url: str,
) -> tuple[str, str | None]:
    """
    Parse WorkflowHub URLs such as:

        https://workflowhub.org/workflows/401

        https://workflowhub.org/workflows/401?version=16
    """
    parsed = urlparse(url)

    parts = [part for part in parsed.path.split("/") if part]

    try:
        workflows_index = parts.index("workflows")

        workflow_id = parts[workflows_index + 1]

    except (ValueError, IndexError):
        raise ValueError(f"Invalid WorkflowHub workflow URL: {url}")

    # Also accept:
    #
    #     /workflows/401.json
    #
    workflow_id = workflow_id.removesuffix(".json")

    query = parse_qs(parsed.query)

    requested_version = query.get(
        "version",
        [None],
    )[0]

    return (
        workflow_id,
        requested_version,
    )


def get_workflow_summary(
    workflow_id: str,
) -> dict:
    """
    Return the minimal structure expected by harvest_workflow().

    For dynamic harvesting we can obtain the version information
    directly from WorkflowHub's JSON endpoint.
    """
    workflow_json = get_workflow_json(workflow_id)

    data = workflow_json.get("data") or {}
    attributes = data.get("attributes") or {}

    versions = attributes.get(
        "versions",
        [],
    )

    return {
        "id": workflow_id,
        "url": (f"{WORKFLOW_HUB_URL}/workflows/{workflow_id}"),
        "versions": [
            {
                "id": version.get("version"),
                "name": version.get("version"),
            }
            for version in versions
            if isinstance(version, dict)
        ],
    }


@dynamic_harvest(
    name="workflowhub",
    hosts=[
        "workflowhub.org",
        "workflowhub.eu",
    ],
)
def pipeline_harvest_workflowhub_url(
    workflow_url: str,
    force: bool = False,
) -> HarvestResult:
    Base.metadata.create_all(engine)

    (
        workflow_id,
        requested_version,
    ) = parse_workflowhub_url(workflow_url)

    workflow = get_workflow_summary(workflow_id)

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
                requested_version=requested_version,
                force=force,
            )

            if changed:
                return HarvestResult(
                    pipeline_tag=PIPELINE_TAG,
                    record_ids=[workflow_id],
                    failed_record_ids=[],
                )

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
    default_schedule="0 20 * * 6",
)
def pipeline_harvest_workflowhub(
    limit: int | None = None,
    use_cache: bool = True,
    force: bool = False,
) -> HarvestResult:
    """
    Harvest WorkflowHub JSON metadata and persist its
    normalised representation in PostgreSQL.
    """
    Base.metadata.create_all(engine)

    workflows = get_hub_workflows(use_cache=use_cache)

    if limit is not None:
        workflows = workflows[:limit]

    record_ids: list[str] = []
    failed_record_ids: list[str] = []

    with Session(
        engine,
        expire_on_commit=False,
    ) as session:
        harvested = get_harvested_versions(session)

        try:
            for workflow in workflows:
                workflow_id = str(workflow.get("id"))

                try:
                    changed = harvest_workflow(
                        session=session,
                        workflow=workflow,
                        harvested=harvested,
                        force=force,
                    )

                    if changed:
                        record_ids.append(workflow_id)

                except Exception:
                    session.rollback()

                    failed_record_ids.append(workflow_id)

                    logger.exception(
                        "Failed to harvest WorkflowHub workflow %s",
                        workflow_id,
                    )

            return HarvestResult(
                pipeline_tag=PIPELINE_TAG,
                record_ids=record_ids,
                failed_record_ids=failed_record_ids,
            )

        except Exception:
            session.rollback()
            raise


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

    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-harvest and upsert even when the stored version is already current.",
    )

    args = parser.parse_args()

    if args.url:
        pipeline_harvest_workflowhub_url(
            args.url,
            force=args.force,
        )
    else:
        pipeline_harvest_workflowhub(
            limit=args.limit,
            use_cache=not args.no_cache,
            force=args.force,
        )


if __name__ == "__main__":
    main()
