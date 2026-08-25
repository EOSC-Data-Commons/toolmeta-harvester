from __future__ import annotations

import io
import json
import logging
import zipfile
from pathlib import Path

import requests
import requests_cache

logger = logging.getLogger(__name__)

WORKFLOW_HUB_API = "https://workflowhub.eu/ga4gh/trs/v2"
HUB_CACHE_FILE = "cache/workflowhub_registry.json"

HEADERS = {
    "Accept": "application/json",
}

requests_cache.install_cache(
    "cache/workflowhub_org_cache",
    backend="sqlite",
    expire_after=86400,
)


def get_json(url: str, result: list | None = None) -> list:
    if result is None:
        result = []

    response = requests.get(
        url,
        timeout=30,
        headers=HEADERS,
    )
    response.raise_for_status()

    result.extend(response.json())

    next_page = response.headers.get("next_page")

    if next_page:
        get_json(next_page, result)

    return result


def save_json(data: object, filename: str) -> None:
    path = Path(filename)
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w") as f:
        json.dump(data, f, indent=2)


def load_json(filename: str) -> list:
    with open(filename) as f:
        return json.load(f)


def get_hub_workflows(use_cache: bool = True) -> list:
    """
    Return all workflows exposed by the WorkflowHub TRS API.
    """

    if use_cache and Path(HUB_CACHE_FILE).is_file():
        logger.info("Loading WorkflowHub registry from cache")
        return load_json(HUB_CACHE_FILE)

    workflows = get_json(f"{WORKFLOW_HUB_API}/tools/")

    save_json(
        workflows,
        HUB_CACHE_FILE,
    )

    return workflows


def get_latest_workflow_version(
    workflow: dict,
) -> dict | None:
    versions = workflow.get("versions", [])

    if not versions:
        return None

    return versions[-1]


def get_latest_workflow_version_id(workflow: dict) -> str | None:
    version = get_latest_workflow_version(workflow)

    if not version:
        return None

    return str(version["id"])


def get_rocrate_url(workflow: dict) -> str:
    version = get_latest_workflow_version(workflow)

    if not version:
        raise ValueError(f"Workflow {workflow.get('id')} has no versions")

    version_id = version["id"]

    return f"{workflow['url']}/ro_crate?version={version_id}"


def download_rocrate(workflow: dict) -> dict:
    """
    Download a WorkflowHub RO-Crate and return
    ro-crate-metadata.json as a Python dictionary.
    """

    url = get_rocrate_url(workflow)

    logger.debug(
        "Downloading WorkflowHub RO-Crate: %s",
        url,
    )

    response = requests.get(
        url,
        timeout=30,
    )
    response.raise_for_status()

    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        metadata_files = [
            name
            for name in archive.namelist()
            if Path(name).name == "ro-crate-metadata.json"
        ]

        if not metadata_files:
            raise ValueError("RO-Crate does not contain ro-crate-metadata.json")

        with archive.open(metadata_files[0]) as f:
            return json.load(f)
