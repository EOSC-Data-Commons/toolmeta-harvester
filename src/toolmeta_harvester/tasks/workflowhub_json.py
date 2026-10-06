from __future__ import annotations

import logging
from urllib.parse import urlsplit, urlunsplit

import requests
import requests_cache

logger = logging.getLogger(__name__)

HEADERS = {
    "Accept": "application/json",
}

requests_cache.install_cache(
    "cache/workflowhub_json_cache",
    backend="sqlite",
    expire_after=86400,
)


def get_workflow_json_url(source_url: str) -> str:
    """
    Convert a WorkflowHub workflow URL to its JSON endpoint.

    Example:
        https://workflowhub.eu/workflows/183
        -> https://workflowhub.eu/workflows/183.json
    """
    parts = urlsplit(source_url)

    path = parts.path.rstrip("/")

    if not path.endswith(".json"):
        path = f"{path}.json"

    return urlunsplit(
        (
            parts.scheme,
            parts.netloc,
            path,
            parts.query,
            "",
        )
    )


def download_workflow_json(source_url: str) -> dict:
    """
    Download WorkflowHub JSON metadata for a workflow.
    """

    url = get_workflow_json_url(source_url)

    logger.debug(
        "Downloading WorkflowHub JSON: %s",
        url,
    )

    response = requests.get(
        url,
        timeout=30,
        headers=HEADERS,
    )
    response.raise_for_status()

    return response.json()


def get_internals(workflow: dict) -> dict:
    """
    Return WorkflowHub workflow internals.
    """
    return workflow.get("data", {}).get("attributes", {}).get("internals", {})


def extract_inputs(workflow: dict) -> list[dict]:
    """
    Extract workflow inputs from WorkflowHub JSON.
    """
    return get_internals(workflow).get("inputs", [])


def extract_outputs(workflow: dict) -> list[dict]:
    """
    Extract workflow outputs from WorkflowHub JSON.
    """
    return get_internals(workflow).get("outputs", [])


def extract_inputs_outputs(
    workflow: dict,
) -> tuple[list[dict], list[dict]]:
    return (
        extract_inputs(workflow),
        extract_outputs(workflow),
    )


def download_inputs_outputs(
    source_url: str,
) -> tuple[list[dict], list[dict]]:
    """
    Download WorkflowHub JSON and return its inputs and outputs.
    """
    workflow = download_workflow_json(source_url)

    return extract_inputs_outputs(workflow)


if __name__ == "__main__":
    source_url = "https://workflowhub.eu/workflows/221"

    print(f"Workflow: {source_url}")
    print(f"JSON URL: {get_workflow_json_url(source_url)}")

    workflow = download_workflow_json(source_url)

    inputs, outputs = extract_inputs_outputs(workflow)

    print("\nInputs:")
    for item in inputs:
        print(item)

    print("\nOutputs:")
    for item in outputs:
        print(item)
