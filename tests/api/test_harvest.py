from unittest.mock import Mock

import pytest

from toolmeta_harvester.api import (
    find_dynamic_flow,
    harvest_url,
    normalise_harvest_url,
)
from toolmeta_harvester.flows.registry import HarvestFlow


@pytest.fixture
def github_flow() -> HarvestFlow:
    return HarvestFlow(
        name="github",
        kind="dynamic",
        handler=Mock(return_value={"source": "github"}),
        hosts=("github.com",),
    )


@pytest.fixture
def zenodo_flow() -> HarvestFlow:
    return HarvestFlow(
        name="zenodo",
        kind="dynamic",
        handler=Mock(return_value={"source": "zenodo"}),
        hosts=("zenodo.org",),
        matcher=lambda url: "/records/" in url,
    )


def test_normalise_harvest_url_strips_whitespace(monkeypatch):
    monkeypatch.setattr(
        "toolmeta_harvester.api.is_doi_url",
        lambda url: False,
    )

    result = normalise_harvest_url("  https://github.com/example/tool  ")

    assert result == "https://github.com/example/tool"


def test_normalise_harvest_url_resolves_doi(monkeypatch):
    monkeypatch.setattr(
        "toolmeta_harvester.api.is_doi_url",
        lambda url: True,
    )
    monkeypatch.setattr(
        "toolmeta_harvester.api.resolve_doi_url",
        lambda url: "https://zenodo.org/records/123",
    )

    result = normalise_harvest_url("https://doi.org/10.5281/zenodo.123")

    assert result == "https://zenodo.org/records/123"


def test_find_dynamic_flow_by_host(monkeypatch, github_flow):
    monkeypatch.setattr(
        "toolmeta_harvester.api.get_dynamic_flows",
        lambda: [github_flow],
    )

    flow = find_dynamic_flow("https://github.com/example/tool")

    assert flow is github_flow


def test_find_dynamic_flow_accepts_subdomain(monkeypatch, github_flow):
    monkeypatch.setattr(
        "toolmeta_harvester.api.get_dynamic_flows",
        lambda: [github_flow],
    )

    flow = find_dynamic_flow("https://www.github.com/example/tool")

    assert flow is github_flow


def test_find_dynamic_flow_uses_matcher(monkeypatch, zenodo_flow):
    # Deliberately use a host not listed in `hosts`, proving that the
    # matcher can independently select the flow.
    monkeypatch.setattr(
        "toolmeta_harvester.api.get_dynamic_flows",
        lambda: [zenodo_flow],
    )

    flow = find_dynamic_flow("https://sandbox.zenodo.example/records/123")

    assert flow is zenodo_flow


def test_find_dynamic_flow_rejects_invalid_url():
    with pytest.raises(ValueError, match="Invalid URL"):
        find_dynamic_flow("not a URL")


def test_find_dynamic_flow_rejects_unsupported_host(monkeypatch):
    monkeypatch.setattr(
        "toolmeta_harvester.api.get_dynamic_flows",
        lambda: [],
    )

    with pytest.raises(ValueError, match="Unsupported harvest URL"):
        find_dynamic_flow("https://example.org/tool")


def test_harvest_url_detects_and_calls_pipeline(
    monkeypatch,
    github_flow,
):
    monkeypatch.setattr(
        "toolmeta_harvester.api.is_doi_url",
        lambda url: False,
    )
    monkeypatch.setattr(
        "toolmeta_harvester.api.get_dynamic_flows",
        lambda: [github_flow],
    )

    result = harvest_url("https://github.com/example/tool")

    assert result == {"source": "github"}
    github_flow.handler.assert_called_once_with("https://github.com/example/tool")


def test_harvest_url_resolves_doi_before_detection(
    monkeypatch,
    zenodo_flow,
):
    resolved_url = "https://zenodo.org/records/123"

    monkeypatch.setattr(
        "toolmeta_harvester.api.is_doi_url",
        lambda url: True,
    )
    monkeypatch.setattr(
        "toolmeta_harvester.api.resolve_doi_url",
        lambda url: resolved_url,
    )
    monkeypatch.setattr(
        "toolmeta_harvester.api.get_dynamic_flows",
        lambda: [zenodo_flow],
    )

    result = harvest_url("https://doi.org/10.5281/zenodo.123")

    assert result == {"source": "zenodo"}
    zenodo_flow.handler.assert_called_once_with(resolved_url)


def test_harvest_url_uses_explicit_source(
    monkeypatch,
    github_flow,
):
    monkeypatch.setattr(
        "toolmeta_harvester.api.is_doi_url",
        lambda url: False,
    )
    monkeypatch.setattr(
        "toolmeta_harvester.api.get_flow",
        lambda name: github_flow,
    )

    result = harvest_url(
        "https://github.com/example/tool",
        source="github",
    )

    assert result == {"source": "github"}
    github_flow.handler.assert_called_once_with("https://github.com/example/tool")


def test_harvest_url_rejects_unknown_explicit_source(monkeypatch):
    monkeypatch.setattr(
        "toolmeta_harvester.api.is_doi_url",
        lambda url: False,
    )

    def missing_flow(name: str):
        raise KeyError(name)

    monkeypatch.setattr(
        "toolmeta_harvester.api.get_flow",
        missing_flow,
    )

    with pytest.raises(
        ValueError,
        match="Unsupported harvest source: unknown",
    ):
        harvest_url(
            "https://example.org/tool",
            source="unknown",
        )


@pytest.mark.parametrize("kind", ["static", "generic"])
def test_harvest_url_rejects_non_dynamic_flow(
    monkeypatch,
    kind,
):
    flow = HarvestFlow(
        name="example",
        kind=kind,
        handler=Mock(),
    )

    monkeypatch.setattr(
        "toolmeta_harvester.api.is_doi_url",
        lambda url: False,
    )
    monkeypatch.setattr(
        "toolmeta_harvester.api.get_flow",
        lambda name: flow,
    )

    with pytest.raises(
        ValueError,
        match="does not accept a URL",
    ):
        harvest_url(
            "https://example.org/tool",
            source="example",
        )

    flow.handler.assert_not_called()
