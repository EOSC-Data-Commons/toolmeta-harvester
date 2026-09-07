from __future__ import annotations

from typing import Callable

from toolmeta_harvester.flows.harvest_github import (
    pipeline_harvest_github,
)
from toolmeta_harvester.flows.harvest_zenodo import (
    pipeline_harvest_zenodo,
)
from toolmeta_harvester.flows.harvest_workflowhub import (
    pipeline_harvest_workflowhub_url,
)
from toolmeta_harvester.flows.harvest_bioschemas import (
    pipeline_harvest_biotools_url,
)

from urllib.parse import urlparse

HarvestPipeline = Callable[[str], object]
PIPELINES: dict[str, HarvestPipeline] = {
    "github": pipeline_harvest_github,
    "zenodo": pipeline_harvest_zenodo,
    "workflowhub": pipeline_harvest_workflowhub_url,
    "biotools": pipeline_harvest_biotools_url,
}


def detect_source(url: str) -> str:
    host = urlparse(url).hostname

    if not host:
        raise ValueError(f"Invalid URL: {url}")

    host = host.lower()

    if host in {
        "github.com",
        "www.github.com",
    }:
        return "github"

    if host in {
        "zenodo.org",
        "www.zenodo.org",
    }:
        return "zenodo"

    if host in {
        "workflowhub.eu",
        "www.workflowhub.eu",
    }:
        return "workflowhub"

    if host in {
        "bio.tools",
        "www.bio.tools",
    }:
        return "biotools"

    raise ValueError(f"Unsupported harvest URL: {url}")


def harvest_url(
    url: str,
    source: str | None = None,
):
    source = source or detect_source(url)

    try:
        pipeline = PIPELINES[source]
    except KeyError as exc:
        raise ValueError(f"Unsupported harvest source: {source}") from exc

    return pipeline(url)
