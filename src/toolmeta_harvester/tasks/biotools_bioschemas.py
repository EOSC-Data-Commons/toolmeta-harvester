from __future__ import annotations

import logging
from urllib.parse import urlencode

import requests


logger = logging.getLogger(__name__)

BIOTOOLS_API = "https://bio.tools/api"
BIOTOOLS_BASE_URL = "https://bio.tools"

HEADERS = {
    "Accept": "application/json",
    "User-Agent": "toolmeta-harvester/1.0",
}


def get_biotools_source_url(
    biotools_id: str,
) -> str:
    return f"{BIOTOOLS_BASE_URL}/{biotools_id}"


def get_biotools_metadata_url(
    biotools_id: str,
) -> str:
    return f"{BIOTOOLS_API}/{biotools_id}/?format=json"


def get_biotools_page(
    page: int = 1,
    per_page: int = 50,
) -> dict:
    """
    Retrieve one page of biotoolsSchema records.
    """

    params = {
        "page": page,
        "per_page": per_page,
        "format": "json",
    }

    url = f"{BIOTOOLS_API}/t/?{urlencode(params)}"

    logger.debug(
        "Fetching bio.tools page %s",
        url,
    )

    response = requests.get(
        url,
        timeout=30,
        headers=HEADERS,
    )

    response.raise_for_status()

    return response.json()


def iter_biotools(
    limit: int | None = None,
    per_page: int = 50,
):
    """
    Iterate over all bio.tools records using the paginated API.
    """

    page = 1
    yielded = 0

    while True:
        payload = get_biotools_page(
            page=page,
            per_page=per_page,
        )

        tools = payload.get(
            "list",
            [],
        )

        if not tools:
            return

        for tool in tools:
            yield tool

            yielded += 1

            if limit is not None and yielded >= limit:
                return

        if not payload.get("next"):
            return

        page += 1


def get_biotools_id(
    tool: dict,
) -> str:
    value = tool.get("biotoolsID") or tool.get("id")

    if not value:
        raise ValueError("bio.tools record has no biotoolsID")

    return str(value)


def get_biotools_record(
    biotools_id: str,
) -> dict:
    """
    Fetch the full biotoolsSchema JSON representation for one tool.
    """

    url = get_biotools_metadata_url(biotools_id)

    logger.info(
        "Fetching bio.tools record %s",
        biotools_id,
    )

    response = requests.get(
        url,
        timeout=30,
        headers=HEADERS,
    )

    response.raise_for_status()

    return response.json()
