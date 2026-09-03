from __future__ import annotations

import argparse
import logging
import os
from datetime import datetime

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from toolmeta_harvester.converters.citation_cff_jsonld import (
    convert_citation_cff_to_jsonld,
)
from toolmeta_harvester.converters.gitlab_jsonld import (
    convert_gitlab_to_jsonld,
    merge_jsonld,
)
from toolmeta_harvester.converters.package_jsonld import (
    convert_package_json_to_jsonld,
)
from toolmeta_harvester.converters.pyproject_jsonld import (
    convert_pyproject_to_jsonld,
)
from toolmeta_harvester.db.engine import engine
from toolmeta_harvester.db.models import (
    Base,
    HarvestResult,
    ToolMetadata,
)
from toolmeta_harvester.extractors.tool_metadata import extract_tool_metadata
from toolmeta_harvester.flows.decorators import dynamic_harvest
from toolmeta_harvester.quality.metadata_quality import assess_metadata_quality
from toolmeta_harvester.tasks.gitlab import (
    get_file_api_url,
    get_file_text,
    get_json_file,
    get_languages,
    get_project,
    get_readme,
    parse_gitlab_url,
    is_gitlab_url,
)


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
        logger.warning(
            "Unable to parse datetime %r",
            value,
        )
        return None


def _canonical_version(metadata: dict) -> str | None:
    value = metadata.get("version")

    if value is None:
        return None

    if isinstance(value, list):
        return ", ".join(str(v) for v in value)

    return str(value)


def create_tool_metadata(
    *,
    project: dict,
    source_metadata: dict,
    metadata: dict,
    metadata_url: str,
    metadata_format: str,
    pipeline_tag: str = PIPELINE_TAG,
) -> ToolMetadata:
    quality = assess_metadata_quality(metadata)

    return ToolMetadata(
        quality_score=quality.score,
        pipeline_tag=pipeline_tag,
        source_identifier=project.get("path_with_namespace"),
        source_url=project.get("web_url"),
        metadata_url=metadata_url,
        metadata_format=metadata_format,
        metadata_version=metadata.get("metadata_version"),
        title=metadata.get("title"),
        description=metadata.get("description"),
        raw_description=metadata.get("raw_description"),
        version=_canonical_version(metadata),
        license=metadata.get("license"),
        identifiers=metadata.get("identifiers", []),
        url=metadata.get("url"),
        code_repository=metadata.get("code_repository"),
        keywords=metadata.get("keywords", []),
        authors=metadata.get("authors", []),
        organizations=metadata.get("organizations", []),
        types=metadata.get("types", []),
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
        inputs=metadata.get("inputs", []),
        outputs=metadata.get("outputs", []),
        date_created=parse_datetime(metadata.get("date_created")),
        date_published=parse_datetime(metadata.get("date_published")),
        date_modified=parse_datetime(metadata.get("date_modified")),
        raw_metadata=source_metadata,
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


def _build_fallback_metadata(
    *,
    instance_url: str,
    project_path: str,
    project: dict,
    token: str | None,
) -> tuple[dict, dict, str]:
    branch = project.get("default_branch") or "HEAD"

    languages = get_languages(
        instance_url,
        project_path,
        token=token,
    )

    readme = get_readme(
        instance_url,
        project_path,
        ref=branch,
        token=token,
    )

    generated = convert_gitlab_to_jsonld(
        project,
        languages=languages,
        readme=readme,
    )

    raw_files: dict[str, str] = {}

    package_text = get_file_text(
        instance_url,
        project_path,
        "package.json",
        ref=branch,
        token=token,
    )

    if package_text is not None:
        try:
            generated = merge_jsonld(
                generated,
                convert_package_json_to_jsonld(package_text),
            )

            raw_files["package.json"] = package_text

        except Exception:
            logger.exception("Unable to convert package.json")

    pyproject_text = get_file_text(
        instance_url,
        project_path,
        "pyproject.toml",
        ref=branch,
        token=token,
    )

    if pyproject_text is not None:
        try:
            generated = merge_jsonld(
                generated,
                convert_pyproject_to_jsonld(pyproject_text),
            )

            raw_files["pyproject.toml"] = pyproject_text

        except Exception:
            logger.exception("Unable to convert pyproject.toml")

    citation_text = get_file_text(
        instance_url,
        project_path,
        "CITATION.cff",
        ref=branch,
        token=token,
    )

    if citation_text is not None:
        try:
            generated = merge_jsonld(
                generated,
                convert_citation_cff_to_jsonld(citation_text),
            )

            raw_files["CITATION.cff"] = citation_text

        except Exception:
            logger.exception("Unable to convert CITATION.cff")

    raw_source = {
        "project": project,
        "languages": languages,
        "readme": readme,
        "files": raw_files,
        "generated_jsonld": generated,
    }

    metadata_url = project.get("web_url")

    return (
        generated,
        raw_source,
        metadata_url,
    )


@dynamic_harvest(
    name="gitlab",
    hosts=["gitlab.com"],
    matcher=is_gitlab_url,
    default_schedule="0 3 * * *",
)
def pipeline_harvest_gitlab(
    repository_url: str,
    *,
    token: str | None = None,
) -> HarvestResult:
    Base.metadata.create_all(engine)

    token = token or os.getenv("GITLAB_TOKEN")

    instance_url, project_path = parse_gitlab_url(repository_url)

    project = get_project(
        instance_url,
        project_path,
        token=token,
    )

    branch = project.get("default_branch") or "HEAD"

    with Session(
        engine,
        expire_on_commit=False,
    ) as session:
        try:
            record_id = project.get(
                "path_with_namespace",
                project_path,
            )

            codemeta = get_json_file(
                instance_url,
                project_path,
                "codemeta.json",
                ref=branch,
                token=token,
            )

            if codemeta is not None:
                logger.info(
                    "Using codemeta.json for %s",
                    project_path,
                )

                metadata = extract_tool_metadata(codemeta)

                source_metadata = codemeta

                metadata_url = get_file_api_url(
                    instance_url,
                    project_path,
                    "codemeta.json",
                )

                metadata_format = "codemeta"

            else:
                logger.info(
                    "No codemeta.json for %s; using fallback metadata",
                    project_path,
                )

                (
                    generated,
                    source_metadata,
                    metadata_url,
                ) = _build_fallback_metadata(
                    instance_url=instance_url,
                    project_path=project_path,
                    project=project,
                    token=token,
                )

                metadata = extract_tool_metadata(generated)

                metadata_format = "gitlab-derived"

            record = create_tool_metadata(
                project=project,
                source_metadata=source_metadata,
                metadata=metadata,
                metadata_url=metadata_url,
                metadata_format=metadata_format,
                pipeline_tag=PIPELINE_TAG,
            )

            upsert_tool_metadata(
                session,
                record,
            )

            session.commit()

            logger.info(
                "Stored GitLab repository %s (format=%s, quality=%.3f)",
                record_id,
                metadata_format,
                record.quality_score,
            )

            return HarvestResult(
                pipeline_tag=PIPELINE_TAG,
                record_ids=[record_id],
                failed_record_ids=[],
            )

        except Exception:
            session.rollback()
            raise


def main():
    parser = argparse.ArgumentParser(description="Harvest one GitLab repository")

    parser.add_argument(
        "url",
        help="GitLab repository URL",
    )

    parser.add_argument(
        "--token",
        default=None,
    )

    args = parser.parse_args()

    pipeline_harvest_gitlab(
        args.url,
        token=args.token,
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
