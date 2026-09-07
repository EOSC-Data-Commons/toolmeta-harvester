from __future__ import annotations

import io
import json
import logging
import re
import zipfile
from pathlib import Path
from urllib.parse import urlparse

import requests


logger = logging.getLogger(__name__)

ZENODO_API = "https://zenodo.org/api"

HEADERS = {
    "Accept": "application/json",
}


def parse_zenodo_url(url: str) -> str:
    """
    Extract a Zenodo record ID.

    Supports:

        https://zenodo.org/records/123456
        https://zenodo.org/record/123456
        https://zenodo.org/api/records/123456
    """

    parsed = urlparse(url)

    if parsed.netloc not in {
        "zenodo.org",
        "www.zenodo.org",
    }:
        raise ValueError(f"Not a Zenodo URL: {url}")

    match = re.search(
        r"/(?:api/)?records?/(\d+)",
        parsed.path,
    )

    if not match:
        raise ValueError(f"Unable to extract Zenodo record ID from {url}")

    return match.group(1)


def get_zenodo_record(
    record_id: str,
) -> dict:
    """
    Retrieve the published Zenodo record.
    """

    url = f"{ZENODO_API}/records/{record_id}"

    response = requests.get(
        url,
        timeout=30,
        headers=HEADERS,
    )
    response.raise_for_status()

    return response.json()


def get_record_files(
    record: dict,
) -> list[dict]:
    """
    Normalise Zenodo file representations.

    Supports both list-style and InvenioRDM-style `entries`
    representations.
    """

    files = record.get("files", [])

    if isinstance(files, list):
        return files

    if isinstance(files, dict):
        entries = files.get("entries", {})

        if isinstance(entries, dict):
            result = []

            for key, value in entries.items():
                if not isinstance(value, dict):
                    continue

                value = dict(value)
                value.setdefault("key", key)

                result.append(value)

            return result

    return []


def get_file_name(
    file: dict,
) -> str | None:
    return file.get("key") or file.get("filename") or file.get("name")


def get_zenodo_jsonld_url(
    record_id: str,
) -> str:
    return f"https://zenodo.org/records/{record_id}/export/json-ld"


def download_zenodo_jsonld(
    record_id: str,
) -> tuple[dict, str]:
    url = get_zenodo_jsonld_url(record_id)

    logger.info(
        "Downloading Zenodo JSON-LD from %s",
        url,
    )

    response = requests.get(
        url,
        timeout=30,
        headers={
            "Accept": "application/ld+json",
        },
    )

    response.raise_for_status()

    return response.json(), url


def get_file_download_url(
    file: dict,
) -> str | None:
    """
    Return the most appropriate Zenodo file content URL.
    """

    links = file.get("links", {})

    if not isinstance(links, dict):
        return None

    return links.get("content") or links.get("download") or links.get("self")


def download_file(
    file: dict,
) -> bytes:
    url = get_file_download_url(file)

    if not url:
        raise ValueError(f"No download URL for Zenodo file {get_file_name(file)!r}")

    logger.info(
        "Downloading Zenodo file %s",
        get_file_name(file),
    )

    response = requests.get(
        url,
        timeout=60,
    )
    response.raise_for_status()

    return response.content


def read_rocrate_from_zip(
    content: bytes,
) -> dict | None:
    """
    Return ro-crate-metadata.json from a ZIP archive,
    or None when the archive is not an RO-Crate.
    """

    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            candidates = [
                name
                for name in archive.namelist()
                if Path(name).name == "ro-crate-metadata.json"
            ]

            if not candidates:
                return None

            # Prefer the shortest path, normally the crate root.
            metadata_file = min(
                candidates,
                key=lambda value: (
                    len(Path(value).parts),
                    len(value),
                ),
            )

            with archive.open(metadata_file) as handle:
                return json.load(handle)

    except zipfile.BadZipFile:
        return None


def download_zenodo_rocrate(
    record: dict,
) -> tuple[dict, str]:
    """
    Locate and retrieve an RO-Crate from a Zenodo record.

    Returns:

        (crate_metadata, metadata_source_url)

    Supported layouts:

    1. ro-crate-metadata.json deposited directly
    2. RO-Crate packaged inside a ZIP file
    """

    files = get_record_files(record)

    if not files:
        raise ValueError("Zenodo record contains no files")

    # ---------------------------------------------------------
    # First try a directly deposited metadata document.
    # ---------------------------------------------------------

    for file in files:
        name = get_file_name(file)

        if not name:
            continue

        if Path(name).name not in {
            "ro-crate-metadata.json",
            "ro-crate-metadata.jsonld",
        }:
            continue

        content = download_file(file)

        try:
            crate = json.loads(content.decode("utf-8"))
        except (
            UnicodeDecodeError,
            json.JSONDecodeError,
        ) as exc:
            raise ValueError(f"Invalid RO-Crate metadata file: {name}") from exc

        metadata_url = get_file_download_url(file)

        if not metadata_url:
            raise ValueError("RO-Crate metadata URL missing")

        return crate, metadata_url

    # ---------------------------------------------------------
    # Then inspect ZIP archives.
    # ---------------------------------------------------------

    zip_files = [
        file
        for file in files
        if (get_file_name(file) and get_file_name(file).lower().endswith(".zip"))
    ]

    # Prefer files that look explicitly like RO-Crates.
    zip_files.sort(
        key=lambda file: (
            0
            if any(
                token in get_file_name(file).lower()
                for token in (
                    "ro-crate",
                    "rocrate",
                    "crate",
                )
            )
            else 1,
            get_file_name(file),
        )
    )

    for file in zip_files:
        content = download_file(file)

        crate = read_rocrate_from_zip(content)

        if crate is None:
            continue

        metadata_url = get_file_download_url(file)

        if not metadata_url:
            raise ValueError("RO-Crate archive URL missing")

        return crate, metadata_url

    raise ValueError("Zenodo record does not contain an RO-Crate")
