from __future__ import annotations

import base64
from urllib.parse import quote, urlparse

import requests


def parse_gitlab_url(repository_url: str) -> tuple[str, str]:
    """
    Parse a GitLab repository URL.

    Returns:
        instance_url, project_path

    Examples:
        https://gitlab.com/group/project
            -> https://gitlab.com
            -> group/project

        https://gitlab.example.org/group/subgroup/project.git
            -> https://gitlab.example.org
            -> group/subgroup/project
    """

    parsed = urlparse(repository_url)

    if parsed.scheme not in {"http", "https"}:
        raise ValueError(f"Unsupported GitLab URL: {repository_url}")

    if not parsed.hostname:
        raise ValueError(f"Invalid GitLab URL: {repository_url}")

    instance_url = f"{parsed.scheme}://{parsed.netloc}"

    project_path = parsed.path.strip("/")

    if project_path.endswith(".git"):
        project_path = project_path[:-4]

    if not project_path:
        raise ValueError(f"Missing GitLab project path: {repository_url}")

    return instance_url, project_path


def _headers(token: str | None = None) -> dict[str, str]:
    headers = {
        "Accept": "application/json",
    }

    if token:
        headers["PRIVATE-TOKEN"] = token

    return headers


def _project_api_url(
    instance_url: str,
    project_path: str,
) -> str:
    project_id = quote(project_path, safe="")

    return f"{instance_url}/api/v4/projects/{project_id}"


def get_project(
    instance_url: str,
    project_path: str,
    *,
    token: str | None = None,
) -> dict:
    response = requests.get(
        _project_api_url(instance_url, project_path),
        headers=_headers(token),
        timeout=30,
    )

    response.raise_for_status()

    return response.json()


def get_languages(
    instance_url: str,
    project_path: str,
    *,
    token: str | None = None,
) -> dict:
    response = requests.get(
        f"{_project_api_url(instance_url, project_path)}/languages",
        headers=_headers(token),
        timeout=30,
    )

    response.raise_for_status()

    return response.json()


def get_file(
    instance_url: str,
    project_path: str,
    file_path: str,
    *,
    ref: str = "HEAD",
    token: str | None = None,
) -> dict | None:
    project_id = quote(project_path, safe="")
    encoded_file = quote(file_path, safe="")

    response = requests.get(
        (
            f"{instance_url}/api/v4/projects/{project_id}"
            f"/repository/files/{encoded_file}"
        ),
        params={"ref": ref},
        headers=_headers(token),
        timeout=30,
    )

    if response.status_code == 404:
        return None

    response.raise_for_status()def get_file_text(
    instance_url: str,
    project_path: str,
    file_path: str,
    *,
    ref: str = "HEAD",
    token: str | None = None,
) -> str | None:
    file = get_file(
        instance_url,
        project_path,
        file_path,
        ref=ref,
        token=token,
    )

    if file is None:
        return None

    content = file.get("content")

    if content is None:
        return None

    encoding = file.get("encoding")

    if encoding == "base64":
        return base64.b64decode(content).decode("utf-8")

    return content


def get_json_file(
    instance_url: str,
    project_path: str,
    file_path: str,
    *,
    ref: str = "HEAD",
    token: str | None = None,
) -> dict | None:
    import json

    text = get_file_text(
        instance_url,
        project_path,
        file_path,
        ref=ref,
        token=token,
    )

    if text is None:
        return None

    return json.loads(text)


def get_file_api_url(
    instance_url: str,
    project_path: str,
    file_path: str,
) -> str:
    project_id = quote(project_path, safe="")
    encoded_file = quote(file_path, safe="")

    return (
        f"{instance_url}/api/v4/projects/{project_id}"
        f"/repository/files/{encoded_file}"
    )


def get_readme(
    instance_url: str,
    project_path: str,
    *,
    ref: str = "HEAD",
    token: str | None = None,
) -> str | None:
    for filename in (
        "README.md",
        "README.rst",
        "README.adoc",
        "README",
    ):
        content = get_file_text(
            instance_url,
            project_path,
            filename,
            ref=ref,
            token=token,
        )

        if content is not None:
            return content

    return None

    return response.json()

def is_gitlab_url(url: str) -> bool:
    parsed = urlparse(url)

    if not parsed.scheme or not parsed.netloc:
        return False

    instance_url = f"{parsed.scheme}://{parsed.netloc}"

    try:
        response = requests.get(
            f"{instance_url}/api/v4/version",
            timeout=5,
        )

        return response.ok

    except requests.RequestException:
        return False
