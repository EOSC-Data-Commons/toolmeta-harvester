from __future__ import annotations

import argparse
import logging
from typing import Any
from urllib.parse import urlparse, urlencode

from sqlalchemy.orm import Session

from toolmeta_harvester.db.engine import engine
from toolmeta_harvester.db.database import initialize_db
from toolmeta_harvester.db.models import Base, HarvestResult, ToolMetadata
from toolmeta_harvester.extractors.codemeta import extract_codemeta_metadata
from toolmeta_harvester.flows.decorators import static_harvest
from toolmeta_harvester.flows.harvest_github import (
    create_tool_metadata as create_github_tool_metadata,
    upsert_tool_metadata,
)
from toolmeta_harvester.tasks.github import (
    get_directory,
    get_file_api_url,
    get_json_file,
)


PIPELINE_VERSION = "0.1.0"
PIPELINE_TAG = f"custom_tool_list@{PIPELINE_VERSION}"

DEFAULT_URL = "https://github.com/EOSC-Data-Commons/custom-tool-list/tree/main/tools"

OWNER = "EOSC-Data-Commons"
REPO = "custom-tool-list"
REF = "main"

logger = logging.getLogger(__name__)


def is_custom_tool_list_url(url: str) -> bool:
    parsed = urlparse(url)

    return (
        parsed.hostname in {"github.com", "www.github.com"}
        and parsed.path.rstrip("/").lower()
        == f"/{OWNER}/{REPO}/tree/{REF}/tools".lower()
    )


def create_tool_metadata(
    *,
    repository: dict,
    source_metadata: dict,
    metadata: dict,
    metadata_url: str,
    metadata_format: str,
    pipeline_tag: str = PIPELINE_TAG,
) -> ToolMetadata:
    """Reuse the common GitHub metadata mapping."""

    return create_github_tool_metadata(
        repository=repository,
        source_metadata=source_metadata,
        metadata=metadata,
        metadata_url=metadata_url,
        metadata_format=metadata_format,
        pipeline_tag=pipeline_tag,
    )


@static_harvest(
    name="custom_tool_list_all",
    default_schedule="0 20 * * 6",
)
def pipeline_harvest_custom_tool_list(
    repository_url: str = DEFAULT_URL,
) -> HarvestResult:
    """Harvest CodeMeta tools from immediate subdirectories of tools/."""

    if not is_custom_tool_list_url(repository_url):
        raise ValueError(f"Expected custom tool list URL: {DEFAULT_URL}")

    entries = get_directory(
        OWNER,
        REPO,
        "tools",
        ref=REF,
        token="",
    )

    # Base.metadata.create_all(engine)
    initialize_db()

    record_ids: list[str] = []
    failed_record_ids: list[str] = []

    with Session(engine, expire_on_commit=False) as session:
        for entry in entries:
            if entry.get("type") != "dir":
                continue

            path = entry["path"]
            record_id = f"{OWNER}/{REPO}/{path}"

            try:
                metadata_path = f"{path}/codemeta.json"

                # codemeta = get_codemeta(metadata_path)
                codemeta = get_json_file(
                    OWNER,
                    REPO,
                    metadata_path,
                    ref=REF,
                    token="",
                )

                metadata = extract_codemeta_metadata(codemeta)

                source_url = f"https://github.com/{OWNER}/{REPO}/tree/{REF}/{path}"

                metadata["title"] = metadata.get("title") or entry["name"]
                metadata["url"] = metadata.get("url") or source_url

                record = create_tool_metadata(
                    repository={
                        "full_name": record_id,
                        "html_url": source_url,
                    },
                    source_metadata=codemeta,
                    metadata=metadata,
                    metadata_url=(
                        get_file_api_url(
                            OWNER,
                            REPO,
                            metadata_path,
                        )
                        + "?"
                        + urlencode({"ref": REF})
                    ),
                    metadata_format="codemeta",
                    pipeline_tag=PIPELINE_TAG,
                )

                upsert_tool_metadata(session, record)
                session.commit()

                record_ids.append(record_id)

                logger.info(
                    "Stored custom tool %s",
                    record_id,
                )

            except Exception:
                session.rollback()

                failed_record_ids.append(record_id)

                logger.exception(
                    "Unable to harvest custom tool %s",
                    record_id,
                )

    return HarvestResult(
        pipeline_tag=PIPELINE_TAG,
        record_ids=record_ids,
        failed_record_ids=failed_record_ids,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Harvest custom CodeMeta tools into ToolMetadata"
    )
    parser.add_argument(
        "url",
        nargs="?",
        default=DEFAULT_URL,
    )

    args = parser.parse_args()

    result = pipeline_harvest_custom_tool_list(args.url)

    if result.failed_record_ids:
        raise SystemExit(1)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
