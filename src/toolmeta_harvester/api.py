from __future__ import annotations
import logging
from typing import Any
from urllib.parse import urlparse
from toolmeta_harvester.flows.registry import (
    HarvestFlow,
    get_dynamic_flows,
    get_flow,
)
from toolmeta_harvester.tasks.utils import resolve_doi_url, is_doi_url

logger = logging.getLogger(__name__)


def normalise_harvest_url(url: str) -> str:
    url = url.strip()

    if is_doi_url(url):
        return resolve_doi_url(url)

    return url


def host_matches(host: str, registered_host: str) -> bool:
    registered_host = registered_host.lower()
    return host == registered_host or host.endswith(f".{registered_host}")


def find_dynamic_flow(url: str) -> HarvestFlow:
    host = urlparse(url).hostname

    if not host:
        raise ValueError(f"Invalid URL: {url}")

    host = host.lower()

    for flow in get_dynamic_flows():
        if flow.matcher is not None and flow.matcher(url):
            return flow

        if any(host_matches(host, candidate) for candidate in flow.hosts):
            return flow

    raise ValueError(f"Unsupported harvest URL: {url}")


def harvest_url(
    url: str,
    source: str | None = None,
) -> Any:
    resolved_url = normalise_harvest_url(url)

    if source is None:
        flow = find_dynamic_flow(resolved_url)
    else:
        # Ensure decorated flow modules have been loaded.
        get_dynamic_flows()

        try:
            flow = get_flow(source)
        except KeyError as exc:
            raise ValueError(f"Unsupported harvest source: {source}") from exc

        if flow.kind != "dynamic":
            raise ValueError(f"Harvest flow {source!r} does not accept a URL")

        if flow.matcher is not None and not flow.matcher(resolved_url):
            raise ValueError(
                f"URL is not accepted by harvest flow {source!r}: {resolved_url}"
            )

        logger.info(
            "Harvesting URL %s using flow %s (%s)",
            resolved_url,
            flow.name,
            flow.handler.__module__,
        )
    # return
    return flow.handler(resolved_url)
