from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from toolmeta_harvester.db.engine import engine
from toolmeta_harvester.enrichment.pipeline import canonical_json

SAMPLE_SIZE = 100
BIOTOOLS_SIZE = 70


def _nonempty(value: Any) -> bool:
    return value not in (None, "", [], {})


def _semantic_key_counts(value: Any, counts: Counter[str]) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            counts[str(key)] += 1
            _semantic_key_counts(child, counts)
    elif isinstance(value, list):
        for child in value:
            _semantic_key_counts(child, counts)


def _audit(rows: list[dict[str, Any]]) -> dict[str, Any]:
    source_counts = Counter(row["metadata_format"] for row in rows)
    key_counts: Counter[str] = Counter()
    semantic_keys: Counter[str] = Counter()
    sizes = []
    source_details: dict[str, dict[str, Any]] = {}
    for row in rows:
        raw = row["raw_metadata"] or {}
        raw = raw if isinstance(raw, dict) else {"value": raw}
        sizes.append(len(canonical_json(raw).encode("utf-8")))
        key_counts.update(raw.keys())
        _semantic_key_counts(raw, semantic_keys)
    for source in sorted(source_counts):
        records = [row for row in rows if row["metadata_format"] == source]
        source_details[source] = {
            "records": len(records),
            "with_description": sum(_nonempty(r["description"]) for r in records),
            "with_keywords": sum(_nonempty(r["keywords"]) for r in records),
            "with_inputs": sum(_nonempty(r["inputs"]) for r in records),
            "with_outputs": sum(_nonempty(r["outputs"]) for r in records),
            "with_software_types": sum(_nonempty(r["software_types"]) for r in records),
            "with_consumes_data": sum(_nonempty(r["consumes_data"]) for r in records),
            "with_produces_data": sum(_nonempty(r["produces_data"]) for r in records),
        }
    ordered_sizes = sorted(sizes)
    return {
        "record_count": len(rows),
        "source_counts": dict(sorted(source_counts.items())),
        "source_details": source_details,
        "raw_metadata_bytes": {
            "mean": round(sum(sizes) / len(sizes), 1),
            "median": ordered_sizes[len(sizes) // 2],
            "p95": ordered_sizes[math.ceil(0.95 * len(sizes)) - 1],
            "maximum": max(sizes),
        },
        "common_top_level_raw_keys": [
            {"key": key, "count": count} for key, count in key_counts.most_common(40)
        ],
        "common_nested_raw_keys": [
            {"key": key, "count": count} for key, count in semantic_keys.most_common(60)
        ],
        "observations": [
            "bio.tools is the dominant source in this ToolDB snapshot.",
            "Input and output coverage varies substantially by metadata source.",
            "Raw metadata contains nested task, operation, topic, parameter, and format semantics that are not uniformly represented in normalized columns.",
        ],
    }


def _quantile_labels(rows: list[dict[str, Any]], key: str, bins: int) -> dict[str, int]:
    ordered = sorted(rows, key=lambda row: (row[key], str(row["id"])))
    labels = {}
    for index, row in enumerate(ordered):
        labels[str(row["id"])] = min(bins - 1, index * bins // max(len(ordered), 1))
    return labels


def _allocate(
    total: int, capacities: dict[Any, int], *, reserve_each: bool
) -> dict[Any, int]:
    if total < 0 or total > sum(capacities.values()):
        raise ValueError("Quota exceeds the available records")
    keys = sorted(capacities, key=str)
    quotas = {key: 0 for key in keys}
    if reserve_each and total >= len(keys):
        for key in keys:
            quotas[key] = 1
    remaining = total - sum(quotas.values())
    weights = {key: capacities[key] - quotas[key] for key in keys}
    weight_total = sum(weights.values())
    if remaining and weight_total:
        exact = {key: remaining * weights[key] / weight_total for key in keys}
        for key in keys:
            addition = min(weights[key], math.floor(exact[key]))
            quotas[key] += addition
        remainder = total - sum(quotas.values())
        for key in sorted(keys, key=lambda item: (-(exact[item] % 1), str(item))):
            if remainder == 0:
                break
            if quotas[key] < capacities[key]:
                quotas[key] += 1
                remainder -= 1
    return quotas


def create_sample(rows: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any]]:
    sources = Counter(row["metadata_format"] for row in rows)
    if len(rows) < SAMPLE_SIZE:
        raise ValueError(f"ToolDB only has {len(rows)} records; 100 are required")
    if BIOTOOLS_SIZE > sources.get("biotoolsSchema", 0):
        raise ValueError("Not enough BioTools records for the requested target")
    non_biotools = {
        source: count for source, count in sources.items() if source != "biotoolsSchema"
    }
    if sum(non_biotools.values()) < SAMPLE_SIZE - BIOTOOLS_SIZE:
        raise ValueError("Not enough non-BioTools records for the requested target")
    source_quotas = _allocate(
        SAMPLE_SIZE - BIOTOOLS_SIZE, non_biotools, reserve_each=True
    )
    by_source: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_source[row["metadata_format"]].append(row)

    selected: list[tuple[dict[str, Any], str]] = []
    bio_rows = by_source["biotoolsSchema"]
    richness_values = {}
    for row in bio_rows:
        richness_values[str(row["id"])] = sum(
            _nonempty(row[field])
            for field in (
                "description",
                "keywords",
                "types",
                "software_types",
                "consumes_data",
                "produces_data",
                "inputs",
                "outputs",
                "raw_metadata",
            )
        )
    for row in bio_rows:
        row["richness"] = richness_values[str(row["id"])]
        row["description_length"] = len(row["description"] or "")
        row["io_pattern"] = (
            "both"
            if _nonempty(row["inputs"]) and _nonempty(row["outputs"])
            else "input-only"
            if _nonempty(row["inputs"])
            else "output-only"
            if _nonempty(row["outputs"])
            else "neither"
        )
    richness_bins = _quantile_labels(bio_rows, "richness", 4)
    description_bins = _quantile_labels(bio_rows, "description_length", 4)
    strata: dict[tuple[int, int, str], list[dict[str, Any]]] = defaultdict(list)
    for row in bio_rows:
        stratum = (
            richness_bins[str(row["id"])],
            description_bins[str(row["id"])],
            row["io_pattern"],
        )
        strata[stratum].append(row)
    bio_quotas = _allocate(
        BIOTOOLS_SIZE,
        {key: len(value) for key, value in strata.items()},
        reserve_each=False,
    )
    for key in sorted(strata, key=str):
        candidates = sorted(
            strata[key],
            key=lambda row: hashlib.sha256(str(row["id"]).encode()).hexdigest(),
        )
        label = f"biotoolsSchema/richness_q{key[0] + 1}/description_q{key[1] + 1}/inputs_{key[2]}"
        selected.extend((row, label) for row in candidates[: bio_quotas[key]])

    for source in sorted(non_biotools):
        candidates = by_source[source]
        source_richness = {}
        for row in candidates:
            row["richness"] = sum(
                _nonempty(row[field])
                for field in (
                    "description",
                    "keywords",
                    "types",
                    "software_types",
                    "consumes_data",
                    "produces_data",
                    "inputs",
                    "outputs",
                    "raw_metadata",
                )
            )
            source_richness[str(row["id"])] = row["richness"]
            row["description_length"] = len(row["description"] or "")
            row["io_pattern"] = (
                "both"
                if _nonempty(row["inputs"]) and _nonempty(row["outputs"])
                else "input-only"
                if _nonempty(row["inputs"])
                else "output-only"
                if _nonempty(row["outputs"])
                else "neither"
            )
        rich_bins = _quantile_labels(candidates, "richness", 2)
        source_strata: dict[tuple[int, str], list[dict[str, Any]]] = defaultdict(list)
        for row in candidates:
            key = (rich_bins[str(row["id"])], row["io_pattern"])
            source_strata[key].append(row)
        quota = source_quotas[source]
        strata_quotas = _allocate(
            quota,
            {key: len(value) for key, value in source_strata.items()},
            reserve_each=False,
        )
        for key in sorted(source_strata, key=str):
            ranked = sorted(
                source_strata[key],
                key=lambda row: hashlib.sha256(str(row["id"]).encode()).hexdigest(),
            )
            label = f"{source}/richness_q{key[0] + 1}/inputs_{key[1]}"
            selected.extend((row, label) for row in ranked[: strata_quotas[key]])

    if len(selected) != SAMPLE_SIZE:
        raise RuntimeError(f"Sampling produced {len(selected)} records instead of 100")
    selected.sort(key=lambda pair: (pair[0]["metadata_format"], str(pair[0]["id"])))
    ids = [str(row["id"]) for row, _ in selected]
    sample_hash = hashlib.sha256("\n".join(ids).encode()).hexdigest()
    sample = {
        "sample_version": 1,
        "created_at": datetime.now(UTC).isoformat(),
        "database_snapshot": "local tooldb restored from the staging dump",
        "sample_size": SAMPLE_SIZE,
        "strategy": {
            "fixed_source_target": {"biotoolsSchema": BIOTOOLS_SIZE},
            "remaining_records": "proportional source allocation with at least one record per non-BioTools source",
            "biotools_strata": "metadata richness quartile x description length quartile x input/output availability",
            "other_source_strata": "source-specific metadata richness median split x input/output availability",
            "within_stratum_order": "SHA-256 of tool UUID, ascending",
            "same_ids_for_variants": ["A", "B"],
        },
        "source_counts": dict(
            sorted(Counter(row["metadata_format"] for row, _ in selected).items())
        ),
        "sample_sha256": sample_hash,
        "tool_ids": ids,
        "records": [
            {
                "tool_id": str(row["id"]),
                "metadata_format": row["metadata_format"],
                "title": row["title"],
                "description_length": len(row["description"] or ""),
                "metadata_richness": row["richness"],
                "has_inputs": _nonempty(row["inputs"]),
                "has_outputs": _nonempty(row["outputs"]),
                "stratum": stratum,
            }
            for row, stratum in selected
        ],
    }
    audit = _audit(rows)
    return sample, audit


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create or verify the persistent 100-tool experiment sample."
    )
    parser.add_argument("--sample-path", type=Path, required=True)
    parser.add_argument("--audit-path", type=Path, required=True)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    with Session(engine) as session:
        rows = [
            dict(row._mapping)
            for row in session.execute(
                text("""SELECT id, metadata_format, title, description, keywords,
                    types, software_types, consumes_data, produces_data, inputs,
                    outputs, raw_metadata FROM tool_metadata ORDER BY id""")
            )
        ]
    sample, audit = create_sample(rows)
    args.sample_path.parent.mkdir(parents=True, exist_ok=True)
    args.audit_path.parent.mkdir(parents=True, exist_ok=True)
    if args.verify:
        existing = json.loads(args.sample_path.read_text(encoding="utf-8"))
        if existing["tool_ids"] != sample["tool_ids"]:
            raise SystemExit("Sample verification failed: deterministic IDs changed")
        print(json.dumps({"verified": True, "sample_sha256": sample["sample_sha256"]}))
        return
    args.sample_path.write_text(
        json.dumps(sample, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    args.audit_path.write_text(
        json.dumps(audit, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "sample_size": len(sample["tool_ids"]),
                "sample_sha256": sample["sample_sha256"],
                "source_counts": sample["source_counts"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
