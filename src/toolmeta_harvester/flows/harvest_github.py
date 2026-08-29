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
from toolmeta_harvester.converters.github_jsonld import (
    convert_github_to_jsonld,
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
    ToolMetadata,
    HarvestResult,
    ToolHarvestRun,
)
from toolmeta_harvester.extractors.tool_metadata import extract_tool_metadata
from toolmeta_harvester.quality.metadata_quality import assess_metadata_quality
from toolmeta_harvester.tasks.github import (
    get_file_api_url,
    get_file_text,
    get_json_file,
    get_languages,
    get_readme,
    get_repository,
    parse_github_url,
)
from toolmeta_harvester.flows.decorators import dynamic_harvest

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


def create_tool_metadata(
    *,
    repository: dict,
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
        source_identifier=repository.get("full_name"),
        source_url=repository.get("html_url"),
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
        programming_languages=metadata.get("programming_languages", []),
        runtime_platforms=metadata.get("runtime_platforms", []),
        software_requirements=metadata.get("software_requirements", []),
        software_types=metadata.get("software_types", []),
        consumes_data=metadata.get("consumes_data", []),
        produces_data=metadata.get("produces_data", []),
        inputs=metadata.get("inputs", []),
        outputs=metadata.get("outputs", []),
        date_created=parse_datetime(metadata.get("date_created")),
        date_published=parse_datetime(metadata.get("date_published")),
        date_modified=parse_datetime(metadata.get("date_modified")),
        raw_metadata=source_metadata,
    )


def upsert_tool_metadata(session: Session, record: ToolMetadata) -> None:
    excluded_from_insert = {"id", "harvested_at"}
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
    owner: str,
    repo: str,
    repository: dict,
    token: str | None,
) -> tuple[dict, dict, str]:
    branch = repository.get("default_branch")
    languages = get_languages(owner, repo, token=token)
    readme = get_readme(owner, repo, ref=branch, token=token)

    generated = convert_github_to_jsonld(
        repository,
        languages=languages,
        readme=readme,
    )
    raw_files: dict[str, str] = {}

    package_text = get_file_text(owner, repo, "package.json", ref=branch, token=token)
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
        owner, repo, "pyproject.toml", ref=branch, token=token
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

    citation_text = get_file_text(owner, repo, "CITATION.cff", ref=branch, token=token)
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
        "repository": repository,
        "languages": languages,
        "readme": readme,
        "files": raw_files,
        "generated_jsonld": generated,
    }

    return generated, raw_source, repository.get("url")


@dynamic_harvest(
    name="github",
    hosts=["github.com"],
    default_schedule="0 3 * * *",
)
def pipeline_harvest_github(
    repository_url: str,
    *,
    token: str | None = None,
) -> HarvestResult:
    Base.metadata.create_all(engine)

    token = token or os.getenv("GITHUB_TOKEN")
    owner, repo = parse_github_url(repository_url)
    repository = get_repository(owner, repo, token=token)
    branch = repository.get("default_branch")

    with Session(
        engine,
        expire_on_commit=False,
    ) as session:
        try:
            record_id = repository.get("full_name")
            codemeta = get_json_file(
                owner,
                repo,
                "codemeta.json",
                ref=branch,
                token=token,
            )

            if codemeta is not None:
                logger.info("Using codemeta.json for %s/%s", owner, repo)
                metadata = extract_tool_metadata(codemeta)
                source_metadata = codemeta
                metadata_url = get_file_api_url(owner, repo, "codemeta.json")
                metadata_format = "codemeta"
            else:
                logger.info(
                    "No codemeta.json for %s/%s; using fallback metadata",
                    owner,
                    repo,
                )
                generated, source_metadata, metadata_url = _build_fallback_metadata(
                    owner=owner,
                    repo=repo,
                    repository=repository,
                    token=token,
                )
                metadata = extract_tool_metadata(generated)
                metadata_format = "github-derived"

            record = create_tool_metadata(
                repository=repository,
                source_metadata=source_metadata,
                metadata=metadata,
                metadata_url=metadata_url,
                metadata_format=metadata_format,
                pipeline_tag=PIPELINE_TAG,
            )
            upsert_tool_metadata(session, record)

            logger.info(
                "Stored GitHub repository %s (format=%s, quality=%.3f)",
                repository.get("full_name"),
                metadata_format,
                record.quality_score,
            )
            return HarvestResult(
                pipeline_tag=PIPELINE_TAG, record_ids=[record_id], failed_record_ids=[]
            )

        except Exception:
            session.rollback()
            raise


def main():
    parser = argparse.ArgumentParser(
        description="Harvest one GitHub repository into ScienceToolMeta"
    )
    parser.add_argument("url")
    parser.add_argument("--token", default=None)
    args = parser.parse_args()

    pipeline_harvest_github(
        args.url,
        token=args.token,
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
