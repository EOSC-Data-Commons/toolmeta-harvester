from __future__ import annotations

import json
import os
import re
from urllib.parse import urlparse
from dataclasses import dataclass

import requests
from typing import Any

GITHUB_API = "https://api.github.com"

JSON_HEADERS = {
    "Accept": "application/vnd.github+json",
    "User-Agent": "toolmeta-harvester/1.0",
}
RAW_HEADERS = {
    "Accept": "application/vnd.github.raw+json",
    "User-Agent": "toolmeta-harvester/1.0",
}


def _headers(*, raw: bool = False, token: str | None = None) -> dict[str, str]:
    headers = dict(RAW_HEADERS if raw else JSON_HEADERS)
    token = token or os.getenv("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


@dataclass(frozen=True)
class GitHubLocation:
    owner: str
    repo: str
    ref: str | None = None
    path: str | None = None


def parse_github_url(url: str) -> GitHubLocation:
    parsed = urlparse(url)
    parts = [part for part in parsed.path.split("/") if part]

    if len(parts) < 2:
        raise ValueError(f"Invalid GitHub repository URL: {url}")

    owner = parts[0]
    repo = parts[1].removesuffix(".git")

    if len(parts) >= 4 and parts[2] == "tree":
        return GitHubLocation(
            owner=owner,
            repo=repo,
            ref=parts[3],
            path="/".join(parts[4:]) or None,
        )

    return GitHubLocation(
        owner=owner,
        repo=repo,
    )


def get_directory(
    owner: str,
    repo: str,
    path: str,
    *,
    ref: str | None = None,
    token: str | None = None,
) -> list[dict[str, Any]]:
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"

    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    if token:
        headers["Authorization"] = f"Bearer {token}"

    params = {}
    if ref:
        params["ref"] = ref

    response = requests.get(
        url,
        headers=headers,
        params=params,
        timeout=30,
    )
    response.raise_for_status()

    entries = response.json()

    if not isinstance(entries, list):
        raise ValueError(f"GitHub path is not a directory: {path}")

    return [
        {
            "type": entry["type"],
            "name": entry["name"],
            "path": entry["path"],
        }
        for entry in entries
    ]


def get_repository(owner: str, repo: str, *, token: str | None = None) -> dict:
    r = requests.get(
        f"{GITHUB_API}/repos/{owner}/{repo}",
        headers=_headers(token=token),
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


def get_languages(owner: str, repo: str, *, token: str | None = None) -> dict[str, int]:
    r = requests.get(
        f"{GITHUB_API}/repos/{owner}/{repo}/languages",
        headers=_headers(token=token),
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


def get_file_api_url(owner: str, repo: str, path: str) -> str:
    return f"{GITHUB_API}/repos/{owner}/{repo}/contents/{path}"


def get_file_text(
    owner: str,
    repo: str,
    path: str,
    *,
    ref: str | None = None,
    token: str | None = None,
) -> str | None:
    params = {"ref": ref} if ref else {}
    r = requests.get(
        get_file_api_url(owner, repo, path),
        params=params,
        headers=_headers(raw=True, token=token),
        timeout=30,
    )
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return r.text


def get_json_file(
    owner: str,
    repo: str,
    path: str,
    *,
    ref: str | None = None,
    token: str | None = None,
) -> dict | None:
    text = get_file_text(owner, repo, path, ref=ref, token=token)
    if text is None:
        return None
    value = json.loads(text)
    if not isinstance(value, dict):
        raise ValueError(f"{path} does not contain a JSON object")
    return value


def get_readme(
    owner: str,
    repo: str,
    *,
    ref: str | None = None,
    token: str | None = None,
) -> str | None:
    params = {"ref": ref} if ref else {}
    r = requests.get(
        f"{GITHUB_API}/repos/{owner}/{repo}/readme",
        params=params,
        headers=_headers(raw=True, token=token),
        timeout=30,
    )
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return r.text
