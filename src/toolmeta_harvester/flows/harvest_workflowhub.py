from __future__ import annotations

import logging
from pathlib import Path
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from toolmeta_harvester.db.engine import engine
from toolmeta_harvester.db.models import (
    Base,
    ToolHarvestRun,
    ToolMetadata,
)
from toolmeta_harvester.extractors.extract_ro_crate_metadata import (
    extract_ro_crate_metadata,
)
from toolmeta_harvester.quality.metadata_quality import (
    assess_metadata_quality,
)
from toolmeta_harvester.tasks.workflowhub_rocrate import (
    download_rocrate,
    get_hub_workflows,
    get_latest_workflow_version_id,
    get_rocrate_url,
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


# def get_version(metadata: dict, workflow: dict) -> str | None:
#     """
#     Get the version of the workflow from the metadata or the workflow object.
#     """
#
#     version = metadata.get("version")
#
#     if version:
#         return str(version).strip()
#
#     version_obj = get_latest_workflow_version(workflow)
#
#     if version_obj:
#         return str(version_obj.get("name")).strip()
#
#     return None
#


def create_tool_metadata(
    workflow: dict,
    crate: dict,
    harvest_run_id,
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
        harvest_run_id=harvest_run_id,
        quality_score=quality.score,
        # ---------------------------------------------------------
        # Provenance
        # ---------------------------------------------------------
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
) -> set[tuple[str, str]]:
    rows = session.execute(
        select(
            ToolMetadata.source_identifier,
            ToolMetadata.version,
        ).where(ToolMetadata.metadata_format == "ro-crate")
    )

    return {
        (str(source_id), str(version))
        for source_id, version in rows
        if source_id is not None and version is not None
    }


def pipeline_harvest_workflowhub(
    limit: int | None = None,
    use_cache: bool = True,
) -> ToolHarvestRun:
    """
    Harvest WorkflowHub RO-Crates and persist their normalised
    metadata in PostgreSQL.
    """

    Base.metadata.create_all(engine)

    workflows = get_hub_workflows(use_cache=use_cache)

    if limit is not None:
        workflows = workflows[:limit]

    harvested_count = 0
    failed_count = 0

    with Session(engine) as session:
        harvested = get_harvested_versions(session)
        harvest_run = ToolHarvestRun(
            source="workflowhub",
            source_url="https://workflowhub.eu",
            status="running",
        )

        session.add(harvest_run)
        session.commit()
        session.refresh(harvest_run)

        harvest_run_id = harvest_run.id

        # logger.info(
        #     "Started WorkflowHub harvest %s",
        #     harvest_run_id,
        # )

        try:
            for workflow in workflows:
                workflow_id = str(workflow.get("id")).strip()
                version = get_latest_workflow_version_id(workflow)

                if not version:
                    logger.warning(
                        "Workflow %s has no versions",
                        workflow_id,
                    )
                    continue

                # version_name = str(version.get("name")).strip()

                key = (
                    workflow_id,
                    version,
                )

                if key in harvested:
                    logger.info(
                        "Skipping WorkflowHub workflow %s "
                        "version %s: already harvested",
                        workflow_id,
                        version,
                    )
                    continue
                else:
                    logger.info(
                        "Harvesting WorkflowHub workflow %s version %s",
                        workflow_id,
                        version,
                    )

                try:
                    logger.info(
                        "Harvesting WorkflowHub workflow %s",
                        workflow_id,
                    )

                    crate = download_rocrate(workflow)

                    tool_metadata = create_tool_metadata(
                        workflow=workflow,
                        crate=crate,
                        harvest_run_id=harvest_run_id,
                    )

                    session.add(tool_metadata)
                    session.commit()

                    harvested.add(key)

                    harvested_count += 1

                    logger.info(
                        "Stored metadata for WorkflowHub workflow %s: %s",
                        workflow_id,
                        tool_metadata.title,
                    )

                except Exception:
                    session.rollback()

                    failed_count += 1

                    logger.exception(
                        "Failed to harvest WorkflowHub workflow %s",
                        workflow_id,
                    )

            harvest_run = session.get(
                ToolHarvestRun,
                harvest_run_id,
            )

            harvest_run.harvested_count = harvested_count
            harvest_run.failed_count = failed_count
            harvest_run.finished_at = datetime.now().astimezone()

            if failed_count:
                harvest_run.status = "completed_with_errors"
            else:
                harvest_run.status = "completed"

            session.commit()
            session.refresh(harvest_run)

            logger.info(
                "WorkflowHub harvest completed: %d harvested, %d failed",
                harvested_count,
                failed_count,
            )

            return harvest_run

        except Exception as exc:
            session.rollback()

            harvest_run = session.get(
                ToolHarvestRun,
                harvest_run_id,
            )

            harvest_run.harvested_count = harvested_count
            harvest_run.failed_count = failed_count
            harvest_run.finished_at = datetime.now().astimezone()
            harvest_run.status = "failed"

            session.commit()

            logger.exception("WorkflowHub harvest failed")

            raise exc


def main():
    pipeline_harvest_workflowhub()
    # Base.metadata.create_all(engine)
    #
    # # workflows = get_hub_workflows(use_cache=use_cache)
    # with Session(engine) as session:
    #     harvested_versions = get_harvested_versions(session)
    #     # print(harvested_versions)
    #     if ("2", "1") in harvested_versions:
    #         logger.info(
    #             "WorkflowHub workflow 1741 version 1 has already been harvested."
    #         )
    #     else:
    #         logger.info(
    #             "WorkflowHub workflow 1741 version 1 has not been harvested yet."
    #         )


if __name__ == "__main__":
    main()
