from __future__ import annotations

from collections import Counter
from uuid import uuid4

from scripts.create_experiment_sample import create_sample


def _row(source: str, index: int) -> dict:
    has_input = index % 4 in {0, 1}
    has_output = index % 4 in {0, 2}
    return {
        "id": uuid4(),
        "metadata_format": source,
        "title": f"Tool {source} {index}",
        "description": "A scientific tool description " * (1 + index % 5),
        "keywords": ["science", f"topic-{index % 7}"],
        "types": ["Command-line tool"],
        "software_types": [{"name": "Application"}] if index % 2 else [],
        "consumes_data": [],
        "produces_data": [],
        "inputs": [{"type": "file"}] if has_input else [],
        "outputs": [{"type": "result"}] if has_output else [],
        "raw_metadata": {"function": {"operation": f"task-{index % 5}"}},
    }


def test_sample_is_exactly_100_reproducible_and_covers_sources():
    rows = [_row("biotoolsSchema", i) for i in range(70)]
    for source in ("workflowhub-json", "codemeta", "boutiques", "ro-crate", "json-ld"):
        rows.extend(_row(source, i) for i in range(6))

    first, audit = create_sample(rows)
    second, _ = create_sample(list(reversed(rows)))

    assert len(first["tool_ids"]) == 100
    assert len(set(first["tool_ids"])) == 100
    assert first["tool_ids"] == second["tool_ids"]
    assert first["sample_sha256"] == second["sample_sha256"]
    assert first["source_counts"]["biotoolsSchema"] == 70
    assert (
        sum(
            value
            for key, value in first["source_counts"].items()
            if key != "biotoolsSchema"
        )
        == 30
    )
    assert set(first["source_counts"]) == {
        "biotoolsSchema",
        "workflowhub-json",
        "codemeta",
        "boutiques",
        "ro-crate",
        "json-ld",
    }
    assert Counter(
        item["stratum"].split("/")[0] for item in first["records"]
    ) == Counter(first["source_counts"])
    assert audit["record_count"] == 100
    assert audit["common_nested_raw_keys"]
