from __future__ import annotations

import csv
import difflib
import html
import json
import math
import statistics
from collections import Counter
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from toolmeta_harvester.db.models import ToolEmbedding, ToolEnrichment, ToolMetadata
from toolmeta_harvester.enrichment.pipeline import SESSION_FACTORY, canonical_json

SCORE_FIELDS = (
    "accuracy_score",
    "completeness_score",
    "input_quality_score",
    "output_quality_score",
    "enriched_description_score",
    "semantic_usefulness_score",
)
REVIEW_FIELDS = ("reviewer", "judgment", "score_A", "score_B", "notes")


def cosine_similarity(
    left: list[float] | None, right: list[float] | None
) -> float | None:
    if not left or not right or len(left) != len(right):
        return None
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return None
    return dot / (left_norm * right_norm)


def _summary(values: list[float]) -> dict[str, float | int | None]:
    if not values:
        return {
            "count": 0,
            "mean": None,
            "median": None,
            "p95": None,
            "min": None,
            "max": None,
        }
    ordered = sorted(values)
    return {
        "count": len(values),
        "mean": round(statistics.mean(values), 4),
        "median": round(statistics.median(values), 4),
        "p95": round(ordered[math.ceil(0.95 * len(ordered)) - 1], 4),
        "min": round(min(values), 4),
        "max": round(max(values), 4),
    }


def _score_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    result = {}
    for field in SCORE_FIELDS:
        values = [
            float(row["validation"][field])
            for row in rows
            if isinstance(row.get("validation"), dict)
            and isinstance(row["validation"].get(field), (int, float))
        ]
        result[field] = _summary(values)
    result["hallucination_flags"] = sum(
        bool((row.get("validation") or {}).get("hallucination_detected"))
        for row in rows
    )
    result["validated_records"] = sum(
        row.get("validation_status") == "completed" for row in rows
    )
    result["deterministic_passes"] = sum(
        bool((row.get("deterministic_validation") or {}).get("passed")) for row in rows
    )
    return result


def analyze_experiment(
    *,
    experiment_id: UUID | str,
    sample_path: str | Path,
    session_factory: sessionmaker[Session] = SESSION_FACTORY,
    airflow_metrics_path: str | Path | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    experiment_id = UUID(str(experiment_id))
    sample = json.loads(Path(sample_path).read_text(encoding="utf-8"))
    sample_ids = [UUID(value) for value in sample["tool_ids"]]
    with session_factory() as session:
        joined = session.execute(
            select(ToolMetadata, ToolEnrichment)
            .join(ToolEnrichment, ToolEnrichment.tool_id == ToolMetadata.id)
            .where(
                ToolEnrichment.experiment_id == experiment_id,
                ToolEnrichment.tool_id.in_(sample_ids),
            )
            .order_by(
                ToolMetadata.metadata_format, ToolMetadata.title, ToolEnrichment.variant
            )
        ).all()
        embeddings = session.scalars(
            select(ToolEmbedding)
            .join(ToolEnrichment, ToolEmbedding.enrichment_id == ToolEnrichment.id)
            .where(ToolEnrichment.experiment_id == experiment_id)
        ).all()

    by_tool: dict[str, dict[str, Any]] = {}
    for tool, result in joined:
        key = str(tool.id)
        comparison = by_tool.setdefault(
            key,
            {
                "tool_id": key,
                "source": tool.metadata_format,
                "title": tool.title,
                "source_metadata": {
                    "description": tool.description,
                    "raw_description": tool.raw_description,
                    "keywords": tool.keywords,
                    "types": tool.types,
                    "software_types": tool.software_types,
                    "inputs": tool.inputs,
                    "outputs": tool.outputs,
                    "consumes_data": tool.consumes_data,
                    "produces_data": tool.produces_data,
                    "raw_metadata": tool.raw_metadata,
                },
            },
        )
        comparison[result.variant] = {
            "enrichment_id": str(result.id),
            "status": result.status,
            "extraction_used": result.extraction_used,
            "extraction_result": result.extraction_result,
            "enriched_description": result.enriched_description,
            "deterministic_validation": result.deterministic_validation,
            "validation": result.validation,
            "validation_status": result.validation_status,
            "requested_extraction_model": result.requested_extraction_model,
            "extraction_model": result.extraction_model,
            "requested_model": result.requested_model,
            "model": result.model,
            "requested_validation_model": result.requested_validation_model,
            "validation_model": result.validation_model,
            "extraction_prompt_version": result.extraction_prompt_version,
            "prompt_version": result.prompt_version,
            "validation_prompt_version": result.validation_prompt_version,
            "source_hash": result.source_hash,
            "extraction_input_hash": result.extraction_input_hash,
            "input_hash": result.input_hash,
            "request_counts": {
                "extraction": result.extraction_request_count,
                "generation": result.generation_request_count,
                "validation": result.validation_request_count,
            },
            "elapsed_seconds": {
                "extraction": result.extraction_elapsed_seconds,
                "generation": result.generation_elapsed_seconds,
                "validation": result.validation_elapsed_seconds,
            },
            "error": result.error,
            "failed_stage": result.failed_stage,
            "created_at": result.created_at.isoformat() if result.created_at else None,
        }

    embeddings_by_result = {str(item.enrichment_id): item for item in embeddings}
    pairs = []
    for tool_id in sample["tool_ids"]:
        item = by_tool.get(tool_id)
        if item is None:
            pairs.append({"tool_id": tool_id, "missing_result": True})
            continue
        for variant in ("A", "B"):
            record = item.get(variant)
            if record:
                vector = embeddings_by_result.get(record["enrichment_id"])
                record["embedding"] = (
                    {
                        "embedding_model": vector.embedding_model,
                        "actual_model": vector.actual_model,
                        "dimensions": len(vector.vector),
                        "batch_id": str(vector.embedding_batch_id)
                        if vector.embedding_batch_id
                        else None,
                        "request_count": vector.request_count,
                        "elapsed_seconds": vector.elapsed_seconds,
                    }
                    if vector
                    else None
                )
                record["_vector"] = list(vector.vector) if vector else None
        a = item.get("A", {})
        b = item.get("B", {})
        similarity = cosine_similarity(a.get("_vector"), b.get("_vector"))
        item["embedding_cosine_similarity"] = similarity
        item["lexical_similarity"] = difflib.SequenceMatcher(
            None,
            (a.get("enriched_description") or "").casefold(),
            (b.get("enriched_description") or "").casefold(),
        ).ratio()
        pairs.append(item)
    for item in pairs:
        for variant in ("A", "B"):
            if variant in item:
                item[variant].pop("_vector", None)

    variant_rows = {
        variant: [
            item[variant] for item in pairs if isinstance(item.get(variant), dict)
        ]
        for variant in ("A", "B")
    }
    metric_differences = {}
    relative = Counter()
    for field in SCORE_FIELDS:
        a_values = [
            row["validation"][field]
            for row in variant_rows["A"]
            if isinstance(row.get("validation"), dict)
            and isinstance(row["validation"].get(field), (int, float))
        ]
        b_values = [
            row["validation"][field]
            for row in variant_rows["B"]
            if isinstance(row.get("validation"), dict)
            and isinstance(row["validation"].get(field), (int, float))
        ]
        paired = []
        for pair in pairs:
            a_score = (pair.get("A", {}).get("validation") or {}).get(field)
            b_score = (pair.get("B", {}).get("validation") or {}).get(field)
            if isinstance(a_score, (int, float)) and isinstance(b_score, (int, float)):
                paired.append(float(b_score) - float(a_score))
                if field == "enriched_description_score":
                    if a_score <= 2 and b_score <= 2:
                        relative["both_poor"] += 1
                    elif b_score > a_score:
                        relative["B_better"] += 1
                    elif a_score > b_score:
                        relative["A_better"] += 1
                    else:
                        relative["similar"] += 1
        metric_differences[field] = {
            "A": _summary([float(value) for value in a_values]),
            "B": _summary([float(value) for value in b_values]),
            "paired_delta_B_minus_A": _summary(paired),
        }
    for key in ("A_better", "B_better", "similar", "both_poor"):
        relative.setdefault(key, 0)

    latencies = {}
    request_counts = {}
    request_count_distributions = {}
    for variant in ("A", "B"):
        latencies[variant] = {}
        request_counts[variant] = {}
        request_count_distributions[variant] = {}
        for stage in ("extraction", "generation", "validation"):
            values = [
                float(row["elapsed_seconds"][stage])
                for row in variant_rows[variant]
                if row["elapsed_seconds"].get(stage) is not None
                and row["elapsed_seconds"].get(stage) > 0
            ]
            latencies[variant][stage] = _summary(values)
            request_counts[variant][stage] = sum(
                int(row["request_counts"].get(stage, 0))
                for row in variant_rows[variant]
            )
            request_count_distributions[variant][stage] = {
                str(attempts): count
                for attempts, count in sorted(
                    Counter(
                        int(row["request_counts"].get(stage, 0))
                        for row in variant_rows[variant]
                    ).items()
                )
            }
        latencies[variant]["total_per_tool"] = _summary(
            [
                sum(float(value or 0.0) for value in row["elapsed_seconds"].values())
                for row in variant_rows[variant]
            ]
        )
        request_counts[variant]["llm_total"] = sum(request_counts[variant].values())

    batch_info: dict[str, tuple[float, int, set[str]]] = {}
    for item in pairs:
        for variant in ("A", "B"):
            emb = (item.get(variant) or {}).get("embedding")
            if not emb or not emb.get("batch_id"):
                continue
            existing = batch_info.get(emb["batch_id"])
            if existing:
                existing[2].add(variant)
            else:
                batch_info[emb["batch_id"]] = (
                    float(emb.get("elapsed_seconds") or 0),
                    int(emb.get("request_count") or 0),
                    {variant},
                )
    embedding_metrics = {
        variant: {
            "records": sum(
                bool((item.get(variant) or {}).get("embedding")) for item in pairs
            ),
            "request_count_share": round(
                sum(
                    request_count / len(variants_in_batch)
                    for _, request_count, variants_in_batch in batch_info.values()
                    if variant in variants_in_batch
                ),
                3,
            ),
            "batch_count": sum(
                variant in variants_in_batch
                for _, _, variants_in_batch in batch_info.values()
            ),
            "batch_elapsed_seconds": _summary(
                [
                    elapsed
                    for elapsed, _, variants_in_batch in batch_info.values()
                    if variant in variants_in_batch
                ]
            ),
            "batch_elapsed_total_seconds": round(
                sum(
                    elapsed
                    for elapsed, _, variants_in_batch in batch_info.values()
                    if variant in variants_in_batch
                ),
                3,
            ),
            "models": sorted(
                {
                    (item.get(variant) or {}).get("embedding", {}).get("actual_model")
                    for item in pairs
                    if (item.get(variant) or {})
                    .get("embedding", {})
                    .get("actual_model")
                }
            ),
        }
        for variant in ("A", "B")
    }
    similarities = [
        float(item["embedding_cosine_similarity"])
        for item in pairs
        if item.get("embedding_cosine_similarity") is not None
    ]
    lengths = {
        variant: _summary(
            [
                float(len((row.get("enriched_description") or "")))
                for row in variant_rows[variant]
                if row.get("enriched_description")
            ]
        )
        for variant in ("A", "B")
    }
    actual_models = {}
    prompt_versions = {}
    for stage, key in (
        ("extraction", "extraction_model"),
        ("generation", "model"),
        ("validation", "validation_model"),
    ):
        actual_models[stage] = sorted(
            {
                row.get(key)
                for variant in variant_rows.values()
                for row in variant
                if row.get(key)
            }
        )
    for stage, key in (
        ("extraction", "extraction_prompt_version"),
        ("generation", "prompt_version"),
        ("validation", "validation_prompt_version"),
    ):
        prompt_versions[stage] = sorted(
            {
                row.get(key)
                for variant in variant_rows.values()
                for row in variant
                if row.get(key)
            }
        )
    airflow = {}
    if airflow_metrics_path and Path(airflow_metrics_path).exists():
        airflow = json.loads(Path(airflow_metrics_path).read_text(encoding="utf-8"))
    audit_path = Path(sample_path).parent / "raw_metadata_audit.json"
    raw_audit = (
        json.loads(audit_path.read_text(encoding="utf-8"))
        if audit_path.exists()
        else {}
    )
    requested_models = {
        "extraction": sorted(
            {
                row.get("requested_extraction_model")
                for rows in variant_rows.values()
                for row in rows
                if row.get("requested_extraction_model")
            }
        ),
        "generation": sorted(
            {
                row.get("requested_model")
                for rows in variant_rows.values()
                for row in rows
                if row.get("requested_model")
            }
        ),
        "validation": sorted(
            {
                row.get("requested_validation_model")
                for rows in variant_rows.values()
                for row in rows
                if row.get("requested_validation_model")
            }
        ),
    }

    metrics = {
        "experiment_id": str(experiment_id),
        "sample_size": len(sample_ids),
        "sample_sha256": sample.get("sample_sha256"),
        "sample_source_counts": sample.get("source_counts", {}),
        "variants": {
            variant: {
                "rows": len(variant_rows[variant]),
                "successes": sum(
                    row.get("status") == "completed" for row in variant_rows[variant]
                ),
                "failures": sum(
                    row.get("status") == "failed" for row in variant_rows[variant]
                ),
                "validation_failures": sum(
                    row.get("validation_status") == "failed"
                    for row in variant_rows[variant]
                ),
                "deterministic_pass_rate": round(
                    sum(
                        bool((row.get("deterministic_validation") or {}).get("passed"))
                        for row in variant_rows[variant]
                    )
                    / max(len(variant_rows[variant]), 1),
                    4,
                ),
                "llm_evaluation": _score_summary(variant_rows[variant]),
                "description_characters": lengths[variant],
                "actual_generation_models": sorted(
                    {
                        row.get("model")
                        for row in variant_rows[variant]
                        if row.get("model")
                    }
                ),
                "requested_generation_models": sorted(
                    {
                        row.get("requested_model")
                        for row in variant_rows[variant]
                        if row.get("requested_model")
                    }
                ),
                "request_counts": request_counts[variant],
                "request_count_distribution": request_count_distributions[variant],
                "latency_seconds": latencies[variant],
                "embedding": embedding_metrics[variant],
            }
            for variant in ("A", "B")
        },
        "actual_models_by_stage": actual_models,
        "requested_models_by_stage": requested_models,
        "prompt_versions_by_stage": prompt_versions,
        "comparison": {
            "embedding_cosine_similarity": _summary(similarities),
            "paired_llm_score_differences": metric_differences,
            "llm_as_judge_description_score_direction": dict(relative),
            "paired_tools": sum("A" in item and "B" in item for item in pairs),
        },
        "performance": {
            "variants": {
                variant: {
                    "llm_stage_elapsed_total_seconds": round(
                        sum(
                            float(row["elapsed_seconds"].get(stage) or 0.0)
                            for row in variant_rows[variant]
                            for stage in ("extraction", "generation", "validation")
                        ),
                        3,
                    ),
                    "embedding_elapsed_total_seconds": embedding_metrics[variant][
                        "batch_elapsed_total_seconds"
                    ],
                    "llm_requests": request_counts[variant]["llm_total"],
                    "embedding_requests": embedding_metrics[variant][
                        "request_count_share"
                    ],
                }
                for variant in ("A", "B")
            },
            "total_llm_requests": sum(
                request_counts[variant]["llm_total"] for variant in ("A", "B")
            ),
            "total_embedding_requests": sum(
                batch_request_count for _, batch_request_count, _ in batch_info.values()
            ),
            "total_embedding_elapsed_seconds": round(
                sum(elapsed for elapsed, _, _ in batch_info.values()), 3
            ),
            "additional_B_llm_elapsed_seconds_vs_A": round(
                sum(
                    float(row["elapsed_seconds"].get(stage) or 0.0)
                    for row in variant_rows["B"]
                    for stage in ("extraction", "generation", "validation")
                )
                - sum(
                    float(row["elapsed_seconds"].get(stage) or 0.0)
                    for row in variant_rows["A"]
                    for stage in ("extraction", "generation", "validation")
                ),
                3,
            ),
            "additional_B_extraction_elapsed_seconds": round(
                sum(
                    float(row["elapsed_seconds"].get("extraction") or 0.0)
                    for row in variant_rows["B"]
                ),
                3,
            ),
            "additional_B_extraction_requests": request_counts["B"]["extraction"],
            "additional_B_llm_requests_vs_A": (
                request_counts["B"]["llm_total"] - request_counts["A"]["llm_total"]
            ),
            "generation_request_attempts_per_tool": {
                variant: request_count_distributions[variant]["generation"]
                for variant in ("A", "B")
            },
            "time_basis": "Accumulated per-stage API elapsed time; Airflow run wall-clock durations are listed separately.",
        },
        "airflow_runs": airflow,
        "raw_metadata_audit": raw_audit,
        "failures": [
            {
                "tool_id": item["tool_id"],
                "variant": variant,
                "stage": row.get("failed_stage"),
                "error": row.get("error"),
            }
            for item in pairs
            for variant in ("A", "B")
            if (row := item.get(variant))
            and (
                row.get("status") == "failed"
                or row.get("validation_status") == "failed"
            )
        ],
        "human_review": {"reviewed": 0, "status": "pending"},
        "cost_note": "The API response does not expose token usage or price in this run; LLM request counts and elapsed time are reported as measurable cost/latency proxies.",
    }
    return metrics, pairs


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as stream:
        for row in rows:
            stream.write(canonical_json(row) + "\n")


def _write_review_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fields = [
        "tool_id",
        "source",
        "title",
        "source_description",
        "source_metadata_json",
        "extraction_A",
        "description_A",
        "evaluation_A",
        "extraction_B",
        "description_B",
        "evaluation_B",
        "embedding_cosine_similarity",
        *REVIEW_FIELDS,
    ]
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            a, b = row.get("A") or {}, row.get("B") or {}
            writer.writerow(
                {
                    "tool_id": row["tool_id"],
                    "source": row.get("source"),
                    "title": row.get("title"),
                    "source_description": (row.get("source_metadata") or {}).get(
                        "description"
                    ),
                    "source_metadata_json": canonical_json(row.get("source_metadata")),
                    "extraction_A": "",
                    "description_A": a.get("enriched_description"),
                    "evaluation_A": canonical_json(a.get("validation")),
                    "extraction_B": canonical_json(b.get("extraction_result")),
                    "description_B": b.get("enriched_description"),
                    "evaluation_B": canonical_json(b.get("validation")),
                    "embedding_cosine_similarity": row.get(
                        "embedding_cosine_similarity"
                    ),
                    "reviewer": "",
                    "judgment": "",
                    "score_A": "",
                    "score_B": "",
                    "notes": "",
                }
            )


def _html_report(metrics: dict[str, Any], rows: list[dict[str, Any]]) -> str:
    payload = (
        json.dumps(rows, ensure_ascii=False)
        .replace("<", "\\u003c")
        .replace("</", "<\\/")
    )
    variants = metrics["variants"]
    mean_a = variants["A"]["llm_evaluation"]["enriched_description_score"]["mean"]
    mean_b = variants["B"]["llm_evaluation"]["enriched_description_score"]["mean"]
    sim = metrics["comparison"]["embedding_cosine_similarity"]["mean"]
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Tool metadata enrichment A/B experiment</title>
<style>
:root{{color-scheme:light;--ink:#18243b;--muted:#64748b;--line:#dce4ef;--blue:#2563eb;--cyan:#e9f5ff;--green:#e8f7ef;--paper:#f6f8fb}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--paper);color:var(--ink);font:15px/1.55 system-ui,-apple-system,Segoe UI,sans-serif}}
header{{background:linear-gradient(120deg,#12213f,#174ea6);color:white;padding:34px max(24px,calc((100vw - 1200px)/2)) 30px}}
header h1{{margin:0 0 8px;font-size:clamp(25px,4vw,38px)}}header p{{margin:0;color:#d8e6ff;max-width:850px}}
main{{max-width:1200px;margin:auto;padding:24px}}h2{{margin:28px 0 12px}}.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:12px}}
.card,.panel,.tool{{background:white;border:1px solid var(--line);border-radius:14px;box-shadow:0 2px 8px #14213a0a}}
.card{{padding:16px}}.card small,.muted{{color:var(--muted)}}.metric{{display:block;font-size:26px;font-weight:700;margin-top:4px}}
.note{{padding:14px 16px;border-left:4px solid #e4a11b;background:#fff8e5;border-radius:8px;margin:14px 0}}
.controls{{display:flex;flex-wrap:wrap;gap:10px;margin:16px 0}}input,select,button{{font:inherit;padding:9px 12px;border:1px solid var(--line);border-radius:8px;background:white}}button{{cursor:pointer;background:var(--blue);border-color:var(--blue);color:white;font-weight:650}}
.tool{{margin:14px 0;overflow:hidden}}.tool summary{{cursor:pointer;padding:15px 18px;font-weight:700}}.tool summary span{{font-weight:400;color:var(--muted);margin-left:8px}}
.columns{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;padding:0 14px 14px}}.panel{{padding:14px;box-shadow:none;overflow-wrap:anywhere}}.panel h3{{margin:0 0 8px;font-size:16px}}.source{{background:#f8fafc}}.variant-a{{background:#f3f7ff}}.variant-b{{background:#f1fbf6}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;font:13px/1.5 ui-monospace,SFMono-Regular,monospace;margin:8px 0}}
.review{{display:flex;flex-wrap:wrap;gap:8px;padding:0 14px 16px}}.review input[type=text]{{min-width:150px;flex:1}}.badge{{display:inline-block;padding:3px 8px;border-radius:99px;background:var(--cyan);font-size:12px}}footer{{max-width:1200px;margin:auto;color:var(--muted);padding:0 24px 36px}}
@media(max-width:800px){{.columns{{grid-template-columns:1fr}}}}
</style></head><body>
<header><h1>Tool metadata enrichment: baseline vs extraction</h1><p>Experiment <code>{html.escape(metrics["experiment_id"])}</code> · {metrics["sample_size"]} persisted sample tools · sample SHA-256 <code>{html.escape(metrics["sample_sha256"])}</code></p></header>
<main>
<h2>Executive summary</h2><div class="cards">
<div class="card"><small>Variant A · mean description score</small><span class="metric">{mean_a if mean_a is not None else "n/a"} / 5</span></div>
<div class="card"><small>Variant B · mean description score</small><span class="metric">{mean_b if mean_b is not None else "n/a"} / 5</span></div>
<div class="card"><small>Paired embedding cosine similarity</small><span class="metric">{sim if sim is not None else "n/a"}</span></div>
<div class="card"><small>Generated rows A / B</small><span class="metric">{variants["A"]["successes"]} / {variants["B"]["successes"]}</span></div></div>
<div class="note"><b>Interpretation:</b> LLM-as-judge scores are supplementary judgments, not ground truth. Embedding similarity measures semantic closeness, not correctness. Human review is pending; use the side-by-side cards and export a review CSV.</div>
<h2>Automatic metrics</h2><div class="panel"><pre>{html.escape(json.dumps({"variants": variants, "comparison": metrics["comparison"], "actual_models_by_stage": metrics["actual_models_by_stage"], "requested_models_by_stage": metrics["requested_models_by_stage"], "prompt_versions_by_stage": metrics["prompt_versions_by_stage"], "airflow_runs": metrics["airflow_runs"], "raw_metadata_audit": metrics["raw_metadata_audit"]}, indent=2, ensure_ascii=False))}</pre></div>
<h2>LLM-as-judge and deterministic validation</h2><p>Deterministic checks are stored separately from the LLM evaluation. Scores and issues can be inspected for each variant below; validator outputs are model judgments and should not be presented as ground truth.</p>
<h2>Human judgement · review of {len(rows)} comparisons</h2><div class="controls"><input id="search" type="search" placeholder="Filter by title, source, or description"><select id="source"><option value="">All sources</option>{"".join(f"<option>{html.escape(source)}</option>" for source in sorted({r.get("source", "") for r in rows if r.get("source")}))}</select><button id="export">Download completed reviews as CSV</button></div><div id="items"></div>
</main><footer>Generated from ToolDB experiment results. Review selections are kept in this browser until exported; they are not submitted to a server.</footer>
<script>
const rows={payload};const box=document.querySelector('#items');const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]));
const reviewKey=r=>'toolmeta-review-'+r.tool_id;function render(){{const q=document.querySelector('#search').value.toLowerCase();const src=document.querySelector('#source').value;box.innerHTML='';for(const r of rows){{if(r.missing_result)continue;const hay=[r.title,r.source,(r.source_metadata||{{}}).description].join(' ').toLowerCase();if((q&&!hay.includes(q))||(src&&r.source!==src))continue;const state=JSON.parse(localStorage.getItem(reviewKey(r))||'{{}}');const a=r.A||{{}},b=r.B||{{}};const card=document.createElement('details');card.className='tool';card.innerHTML=`<summary>${{esc(r.title||'Untitled')}} <span>${{esc(r.source)}} · cosine ${{r.embedding_cosine_similarity??'n/a'}}</span></summary><div class="columns"><section class="panel source"><h3>Source metadata</h3><p>${{esc((r.source_metadata||{{}}).description)}}</p><b>Keywords</b><pre>${{esc(JSON.stringify((r.source_metadata||{{}}).keywords||[],null,2))}}</pre><b>Inputs / outputs</b><pre>${{esc(JSON.stringify({{inputs:(r.source_metadata||{{}}).inputs,outputs:(r.source_metadata||{{}}).outputs}},null,2))}}</pre><details><summary>All raw metadata</summary><pre>${{esc(JSON.stringify((r.source_metadata||{{}}).raw_metadata,null,2))}}</pre></details></section><section class="panel variant-a"><h3>Variant A · baseline</h3><p>${{esc(a.enriched_description)}}</p><b>Deterministic checks</b><pre>${{esc(JSON.stringify(a.deterministic_validation,null,2))}}</pre><b>LLM-as-judge</b><pre>${{esc(JSON.stringify(a.validation,null,2))}}</pre><span class="badge">${{esc(a.model||'model unknown')}}</span></section><section class="panel variant-b"><h3>Variant B · extraction + generation</h3><details open><summary>Extracted profile</summary><pre>${{esc(JSON.stringify(b.extraction_result,null,2))}}</pre></details><p>${{esc(b.enriched_description)}}</p><b>Deterministic checks</b><pre>${{esc(JSON.stringify(b.deterministic_validation,null,2))}}</pre><b>LLM-as-judge</b><pre>${{esc(JSON.stringify(b.validation,null,2))}}</pre><span class="badge">${{esc(b.model||'model unknown')}}</span></section></div><div class="review"><label>Reviewer <input data-key="reviewer" type="text" value="${{esc(state.reviewer)}}"></label><label>Judgment <select data-key="judgment"><option value="">Choose</option>${{['A better','B better','Similar','Both poor'].map(v=>`<option ${{state.judgment===v?'selected':''}}>${{v}}</option>`).join('')}}</select></label><label>A score <select data-key="score_A"><option value="">—</option>${{[1,2,3,4,5].map(v=>`<option ${{String(state.score_A)===String(v)?'selected':''}}>${{v}}</option>`).join('')}}</select></label><label>B score <select data-key="score_B"><option value="">—</option>${{[1,2,3,4,5].map(v=>`<option ${{String(state.score_B)===String(v)?'selected':''}}>${{v}}</option>`).join('')}}</select></label><input data-key="notes" type="text" placeholder="Review notes" value="${{esc(state.notes)}}"></div>`;card.querySelectorAll('[data-key]').forEach(el=>el.addEventListener('change',()=>{{const data=JSON.parse(localStorage.getItem(reviewKey(r))||'{{}}');data[el.dataset.key]=el.value;localStorage.setItem(reviewKey(r),JSON.stringify(data));}}));box.append(card);}}}}
document.querySelector('#search').addEventListener('input',render);document.querySelector('#source').addEventListener('change',render);document.querySelector('#export').addEventListener('click',()=>{{const fields=['tool_id','source','title',...{json.dumps(REVIEW_FIELDS)}];const csv=[fields.join(',')];for(const r of rows){{const saved=JSON.parse(localStorage.getItem(reviewKey(r))||'{{}}');if(!Object.values(saved).some(Boolean))continue;csv.push([r.tool_id,r.source,r.title,...{json.dumps(REVIEW_FIELDS)}.map(k=>saved[k]||'')].map(v=>'"'+String(v??'').replaceAll('"','""')+'"').join(','));}}const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([csv.join('\\n')],{{type:'text/csv'}}));a.download='manual_review_completed.csv';a.click();URL.revokeObjectURL(a.href);}});render();
</script></body></html>"""


def generate_experiment_artifacts(
    *,
    experiment_id: UUID | str,
    sample_path: str | Path,
    output_dir: str | Path,
    airflow_metrics_path: str | Path | None = None,
) -> dict[str, Any]:
    metrics, rows = analyze_experiment(
        experiment_id=experiment_id,
        sample_path=sample_path,
        airflow_metrics_path=airflow_metrics_path,
    )
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    clean_rows = []
    for row in rows:
        clean = dict(row)
        for variant in ("A", "B"):
            if variant in clean:
                clean[variant] = dict(clean[variant])
        clean_rows.append(clean)
    (out / "metrics.json").write_text(
        json.dumps(metrics, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    _write_jsonl(out / "comparison.jsonl", clean_rows)
    _write_review_csv(out / "manual_review.csv", clean_rows)
    (out / "report.html").write_text(
        _html_report(metrics, clean_rows), encoding="utf-8"
    )
    (out / "EXPERIMENT.md").write_text(_experiment_markdown(metrics), encoding="utf-8")
    return metrics


def _experiment_markdown(metrics: dict[str, Any]) -> str:
    variants = metrics["variants"]
    performance = metrics["performance"]
    lines = [
        "# Tool metadata enrichment experiment",
        "",
        f"- Experiment ID: `{metrics['experiment_id']}`",
        f"- Immutable sample size: {metrics['sample_size']}",
        f"- Sample SHA-256: `{metrics['sample_sha256']}`",
        f"- Sample composition: `{canonical_json(metrics['sample_source_counts'])}`",
        "",
        "## Context and hypothesis",
        "",
        "This experiment tests whether extracting a structured semantic profile before description generation improves factuality, completeness, and usefulness enough to justify extra LLM requests and latency.",
        "",
        "## Methodology",
        "",
        "Variant A generates directly from source metadata. Variant B first extracts a structured semantic profile and supplies that profile to the same generation prompt. Both use the same persisted 100-tool sample. Extraction is the only intended A/B difference.",
        "",
        "Embeddings are generated after successful enrichment through an Airflow Asset dependency. LLM validation runs in an independent DAG and is not an embedding prerequisite. Deterministic checks run on generated descriptions; LLM-as-judge scores are supplementary and are not ground truth.",
        "",
        "The sample stratifies 70 BioTools entries by metadata richness, description length, and input/output coverage, then allocates 30 records across the remaining sources with at least one per source. The sample JSON and raw metadata audit accompany this report.",
        "",
        "## Sample and configuration",
        "",
        f"- Sample composition: `{canonical_json(metrics['sample_source_counts'])}`.",
        f"- Actual models returned by API: `{canonical_json(metrics['actual_models_by_stage'])}`.",
        f"- Requested models: `{canonical_json(metrics['requested_models_by_stage'])}`.",
        f"- Prompt versions: `{canonical_json(metrics['prompt_versions_by_stage'])}`.",
        "- Chat endpoint and embedding endpoint are configured through Dynaconf; secrets are excluded from this artifact.",
        "- Embedding vectors are associated with their exact `tool_enrichments.id`.",
        "",
        "## Raw metadata audit",
        "",
        f"Source-level field coverage and nested raw metadata keys are recorded in `raw_metadata_audit.json`: `{canonical_json(metrics['raw_metadata_audit'].get('source_counts', {}))}`.",
        "",
        "## Actual results",
        "",
        "| Measure | A: baseline | B: extraction + generation |",
        "| --- | ---: | ---: |",
    ]
    for label, field in (
        ("Successful enrichment rows", "successes"),
        ("Failed enrichment rows", "failures"),
        ("LLM validation failures", "validation_failures"),
        ("Deterministic pass rate", "deterministic_pass_rate"),
    ):
        lines.append(f"| {label} | {variants['A'][field]} | {variants['B'][field]} |")
    for field, label in (
        ("accuracy_score", "LLM accuracy mean / 5"),
        ("completeness_score", "LLM completeness mean / 5"),
        ("enriched_description_score", "LLM description quality mean / 5"),
        ("semantic_usefulness_score", "LLM usefulness mean / 5"),
    ):
        a = variants["A"]["llm_evaluation"][field]["mean"]
        b = variants["B"]["llm_evaluation"][field]["mean"]
        lines.append(
            f"| {label} | {a if a is not None else 'n/a'} | {b if b is not None else 'n/a'} |"
        )
    lines.extend(
        [
            "",
            f"- Mean paired embedding cosine similarity: {metrics['comparison']['embedding_cosine_similarity']['mean']} (similarity is not a quality score).",
            f"- Paired LLM-as-judge description-score directions: `{canonical_json(metrics['comparison']['llm_as_judge_description_score_direction'])}`.",
            f"- API request counts (including retries): `{canonical_json({v: variants[v]['request_counts'] for v in ('A', 'B')})}`.",
            f"- Request-attempt distributions by stage (records → attempts): `{canonical_json({v: variants[v]['request_count_distribution'] for v in ('A', 'B')})}`.",
            f"- Per-stage latency summaries: `{canonical_json({v: variants[v]['latency_seconds'] for v in ('A', 'B')})}`.",
            f"- Embedding API metrics: `{canonical_json({v: variants[v]['embedding'] for v in ('A', 'B')})}`.",
            "",
            "## Quality vs cost vs latency",
            "",
            f"- Total LLM requests (all stages, including retries): {performance['total_llm_requests']}.",
            f"- Total embedding requests: {performance['total_embedding_requests']}.",
            f"- Total accumulated embedding API time: {performance['total_embedding_elapsed_seconds']} seconds.",
            f"- Accumulated LLM API time A / B: {performance['variants']['A']['llm_stage_elapsed_total_seconds']} / {performance['variants']['B']['llm_stage_elapsed_total_seconds']} seconds.",
            f"- B extraction added {performance['additional_B_extraction_requests']} LLM requests and {performance['additional_B_extraction_elapsed_seconds']} seconds over A's generation path.",
            f"- Additional total B LLM requests vs A, including validation: {performance['additional_B_llm_requests_vs_A']}.",
            "- Request-count comparison is affected by retries: A generation recorded more than one HTTP attempt per tool, while B generation recorded one. The response status for each attempt was not persisted, so the excess attempts cannot be attributed to a specific transient cause from this run.",
            f"- Accumulated B LLM time minus A: {performance['additional_B_llm_elapsed_seconds_vs_A']} seconds. This sums per-stage API time; it is not Airflow wall-clock duration.",
            "- Provider token usage and price were not returned; request counts and elapsed time are cost proxies, not monetary estimates.",
            "",
            f"- Airflow task-run wall times: `{canonical_json(metrics['airflow_runs'])}`.",
            "- API token usage and monetary pricing were not returned by the service; request count and measured latency are the available cost proxies.",
            "",
            "## Human review",
            "",
            "No human ratings are prefilled. `manual_review.csv` provides one review row per tool with reviewer, A/B judgment, scores, and notes. `report.html` provides a side-by-side viewer and exports completed browser-local judgments to CSV. Automatic and LLM-based judgments remain clearly separate from human ratings.",
            "",
            "## Failures and limitations",
            "",
            f"- Failed enrichment rows: A={variants['A']['failures']}, B={variants['B']['failures']}; see `comparison.jsonl` for per-tool failure stage and error.",
            "- The sample is intentionally source-balanced relative to ToolDB's BioTools-heavy distribution and is not a prevalence-weighted estimate for the full database.",
            "- LLM-as-judge scores can share model biases and are not independent ground truth.",
            "- Embedding similarity indicates semantic closeness only.",
            "- Monetary API cost is unknown without provider token-usage and pricing data.",
            "",
            "## Reproducibility",
            "",
            "The checked-in `representative_sample_100.json` contains the fixed UUIDs and SHA-256. Trigger `tool_metadata_enrichment` twice with the same `experiment_id`, first with `variant: A`, then `variant: B`, and the same `sample_path`. Trigger `tool_metadata_validation` independently for each variant. The enrichment Asset schedules `tool_metadata_embedding` automatically. Re-running a completed variant with unchanged source hashes is idempotent; changed source inputs require a new experiment ID.",
            "",
            "## Conclusion",
            "",
            f"- The LLM judge rated descriptions {variants['A']['llm_evaluation']['enriched_description_score']['mean']}/5 for A and {variants['B']['llm_evaluation']['enriched_description_score']['mean']}/5 for B; paired directions were `{canonical_json(metrics['comparison']['llm_as_judge_description_score_direction'])}`.",
            f"- Mean embedding cosine similarity was {metrics['comparison']['embedding_cosine_similarity']['mean']}, which indicates that the descriptions are semantically close but does not establish factual quality.",
            f"- On this sample and judge, B did not show a clear description-quality gain over A and required more measured LLM time ({performance['variants']['A']['llm_stage_elapsed_total_seconds']} seconds for A vs {performance['variants']['B']['llm_stage_elapsed_total_seconds']} seconds for B). Treat this as a preliminary result: the judge uses the same model family as generation and manual expert ratings are still pending.",
            "- Review the side-by-side HTML and `manual_review.csv` before deciding whether extraction's additional signal justifies its latency. Request totals are confounded by A's higher recorded generation retry count, whose per-attempt response status was not retained.",
            "",
        ]
    )
    return "\n".join(lines)
