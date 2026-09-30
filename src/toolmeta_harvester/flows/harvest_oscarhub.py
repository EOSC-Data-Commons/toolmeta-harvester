from __future__ import annotations

import argparse
import logging
from typing import Any
from urllib.parse import urlencode, urlparse

from sqlalchemy.orm import Session

from toolmeta_harvester.db.engine import engine
from toolmeta_harvester.db.models import Base, HarvestResult, ToolMetadata
from toolmeta_harvester.extractors.common import (
    as_list,
    deduplicate_terms,
    extract_io_entities,
)
from toolmeta_harvester.extractors.ro_crate import (
    build_entity_index,
    extract_ro_crate_metadata,
    get_main_entity,
    get_root_entity,
    is_ro_crate,
    resolve,
)
from toolmeta_harvester.flows.decorators import dynamic_harvest
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
PIPELINE_TAG = f"oscarhub@{PIPELINE_VERSION}"
DEFAULT_URL = "https://github.com/grycap/oscar-hub/tree/main/crates"
OWNER = "grycap"
REPO = "oscar-hub"
REF = "main"
logger = logging.getLogger(__name__)


def is_oscarhub_url(url: str) -> bool:
    parsed = urlparse(url)
    return (
        parsed.hostname in {"github.com", "www.github.com"}
        and parsed.path.rstrip("/") == "/grycap/oscar-hub/tree/main/crates"
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
    """Reuse the common record mapping with OSCAR Hub provenance by default."""
    return create_github_tool_metadata(
        repository=repository,
        source_metadata=source_metadata,
        metadata=metadata,
        metadata_url=metadata_url,
        metadata_format=metadata_format,
        pipeline_tag=pipeline_tag,
    )


def extract_tool_metadata(
    metadata: dict[str, Any],
) -> dict[str, Any]:
    """Extract the service and resolve its linked acceptance-test data."""
    result = extract_ro_crate_metadata(metadata)
    result["types"] = list(dict.fromkeys([*result["types"], "Oscar"]))
    entities = build_entity_index(metadata)
    root = get_root_entity(metadata, entities)
    main = get_main_entity(root, entities) or root

    def resolver(value: Any) -> Any:
        return resolve(value, entities)

    inputs: list[Any] = []
    outputs: list[Any] = []
    for test in as_list(main.get("subjectOf") or root.get("subjectOf")):
        test = resolver(test)
        if not isinstance(test, dict):
            continue
        for supply in as_list(test.get("supply")):
            supply = resolver(supply)
            if isinstance(supply, dict):
                inputs.extend(as_list(supply.get("item")))
        for step in as_list(test.get("step")):
            step = resolver(step)
            if not isinstance(step, dict):
                continue
            for action in as_list(step.get("potentialAction")):
                action = resolver(action)
                if isinstance(action, dict):
                    inputs.extend(as_list(action.get("object")))
                    outputs.extend(as_list(action.get("result")))
    result["inputs"] = deduplicate_terms(
        result["inputs"] + extract_io_entities(inputs, resolver)
    )
    result["outputs"] = deduplicate_terms(
        result["outputs"] + extract_io_entities(outputs, resolver)
    )
    return result


@dynamic_harvest(
    name="oscarhub",
    hosts=[],
    matcher=is_oscarhub_url,
    default_schedule="0 3 * * *",
)
def pipeline_harvest_oscarhub(
    repository_url: str = DEFAULT_URL,
) -> HarvestResult:
    """Store one tool per immediate subdirectory of OSCAR Hub's crates folder."""
    if not is_oscarhub_url(repository_url):
        raise ValueError(f"Expected OSCAR Hub crates URL: {DEFAULT_URL}")

    # An empty token explicitly disables authentication, including environment tokens.
    entries = get_directory(OWNER, REPO, "crates", ref=REF, token="")
    Base.metadata.create_all(engine)
    record_ids: list[str] = []
    failed_record_ids: list[str] = []

    with Session(engine, expire_on_commit=False) as session:
        for entry in entries:
            if entry.get("type") != "dir":
                continue
            path = entry["path"]
            record_id = f"{OWNER}/{REPO}/{path}"
            try:
                metadata_path = f"{path}/ro-crate-metadata.json"
                crate = get_json_file(
                    OWNER,
                    REPO,
                    metadata_path,
                    ref=REF,
                    token="",
                )
                if not isinstance(crate, dict) or not is_ro_crate(crate):
                    raise ValueError(f"Missing or invalid RO-Crate: {metadata_path}")
                metadata = extract_tool_metadata(crate)
                source_url = f"https://github.com/{OWNER}/{REPO}/tree/{REF}/{path}"
                metadata["title"] = metadata.get("title") or entry["name"]
                metadata["url"] = metadata.get("url") or source_url
                record = create_tool_metadata(
                    repository={"full_name": record_id, "html_url": source_url},
                    source_metadata=crate,
                    metadata=metadata,
                    metadata_url=(
                        get_file_api_url(OWNER, REPO, metadata_path)
                        + "?"
                        + urlencode({"ref": REF})
                    ),
                    metadata_format="ro-crate",
                    pipeline_tag=PIPELINE_TAG,
                )
                upsert_tool_metadata(session, record)
                session.commit()
                record_ids.append(record_id)
                logger.info("Stored OSCAR Hub tool %s", record_id)
            except Exception:
                session.rollback()
                failed_record_ids.append(record_id)
                logger.exception("Unable to harvest OSCAR Hub tool %s", record_id)

    return HarvestResult(
        pipeline_tag=PIPELINE_TAG,
        record_ids=record_ids,
        failed_record_ids=failed_record_ids,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Harvest OSCAR Hub crates into ToolMetadata"
    )
    parser.add_argument("url", nargs="?", default=DEFAULT_URL)
    args = parser.parse_args()
    result = pipeline_harvest_oscarhub(args.url)
    if result.failed_record_ids:
        raise SystemExit(1)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
