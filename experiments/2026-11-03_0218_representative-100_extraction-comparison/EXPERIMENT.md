# Tool metadata enrichment experiment

- Experiment ID: `23c03cf7-0c4f-425a-b44d-fb16755605f5`
- Immutable sample size: 100
- Sample SHA-256: `f22fd8dfe61e4a01584a546ad443adaeec7cd1e57a682f6f7212ddb80383d98f`
- Sample composition: `{"biotoolsSchema":70,"boutiques":1,"codemeta":13,"json-ld":1,"ro-crate":1,"workflowhub-json":14}`

## Context and hypothesis

This experiment tests whether extracting a structured semantic profile before description generation improves factuality, completeness, and usefulness enough to justify extra LLM requests and latency.

## Methodology

Variant A generates directly from source metadata. Variant B first extracts a structured semantic profile and supplies that profile to the same generation prompt. Both use the same persisted 100-tool sample. Extraction is the only intended A/B difference.

Embeddings are generated after successful enrichment through an Airflow Asset dependency. LLM validation runs in an independent DAG and is not an embedding prerequisite. Deterministic checks run on generated descriptions; LLM-as-judge scores are supplementary and are not ground truth.

The sample stratifies 70 BioTools entries by metadata richness, description length, and input/output coverage, then allocates 30 records across the remaining sources with at least one per source. The sample JSON and raw metadata audit accompany this report.

## Sample and configuration

- Sample composition: `{"biotoolsSchema":70,"boutiques":1,"codemeta":13,"json-ld":1,"ro-crate":1,"workflowhub-json":14}`.
- Actual models returned by API: `{"extraction":["qwen3.8-27b"],"generation":["qwen3.8-27b"],"validation":["qwen3.8-27b"]}`.
- Requested models: `{"extraction":["qwen3.8-27b"],"generation":["qwen3.8-27b"],"validation":["qwen3.8-27b"]}`.
- Prompt versions: `{"extraction":["extraction_v1"],"generation":["generation_v1"],"validation":["validation_v1"]}`.
- Chat endpoint and embedding endpoint are configured through Dynaconf; secrets are excluded from this artifact.
- Embedding vectors are associated with their exact `tool_enrichments.id`.

## Raw metadata audit

Source-level field coverage and nested raw metadata keys are recorded in `raw_metadata_audit.json`: `{"biotoolsSchema":34445,"boutiques":37,"codemeta":1411,"json-ld":1,"ro-crate":16,"workflowhub-json":1584}`.

## Actual results

| Measure | A: baseline | B: extraction + generation |
| --- | ---: | ---: |
| Successful enrichment rows | 100 | 100 |
| Failed enrichment rows | 0 | 0 |
| LLM validation failures | 0 | 0 |
| Deterministic pass rate | 1.0 | 1.0 |
| LLM accuracy mean / 5 | 4.83 | 4.75 |
| LLM completeness mean / 5 | 4.47 | 4.33 |
| LLM description quality mean / 5 | 4.61 | 4.55 |
| LLM usefulness mean / 5 | 4.36 | 4.21 |

- Mean paired embedding cosine similarity: 0.9694 (similarity is not a quality score).
- Paired LLM-as-judge description-score directions: `{"A_better":27,"B_better":21,"both_poor":0,"similar":52}`.
- API request counts (including retries): `{"A":{"extraction":0,"generation":300,"llm_total":400,"validation":100},"B":{"extraction":100,"generation":100,"llm_total":300,"validation":100}}`.
- Request-attempt distributions by stage (records → attempts): `{"A":{"extraction":{"0":100},"generation":{"3":100},"validation":{"1":100}},"B":{"extraction":{"1":100},"generation":{"1":100},"validation":{"1":100}}}`.
- Per-stage latency summaries: `{"A":{"extraction":{"count":0,"max":null,"mean":null,"median":null,"min":null,"p95":null},"generation":{"count":100,"max":37.4463,"mean":14.0279,"median":12.6921,"min":5.2394,"p95":28.7137},"total_per_tool":{"count":100,"max":131.0027,"mean":48.7113,"median":45.8874,"min":19.6203,"p95":83.7118},"validation":{"count":100,"max":102.7649,"mean":34.6834,"median":31.3586,"min":13.4839,"p95":61.4557}},"B":{"extraction":{"count":100,"max":147.9769,"mean":39.0424,"median":34.3,"min":7.4398,"p95":93.5667},"generation":{"count":100,"max":32.5298,"mean":11.7586,"median":9.7975,"min":2.1954,"p95":26.737},"total_per_tool":{"count":100,"max":238.939,"mean":86.6762,"median":78.4685,"min":33.6535,"p95":155.4453},"validation":{"count":100,"max":84.5806,"mean":35.8752,"median":34.6894,"min":10.9068,"p95":59.674}}}`.
- Embedding API metrics: `{"A":{"batch_count":7,"batch_elapsed_seconds":{"count":7,"max":0.217,"mean":0.1288,"median":0.1196,"min":0.0661,"p95":0.217},"batch_elapsed_total_seconds":0.902,"models":["nomic-embed-text-v2-moe"],"records":100,"request_count_share":7.0},"B":{"batch_count":7,"batch_elapsed_seconds":{"count":7,"max":0.209,"mean":0.1245,"median":0.1211,"min":0.0543,"p95":0.209},"batch_elapsed_total_seconds":0.871,"models":["nomic-embed-text-v2-moe"],"records":100,"request_count_share":7.0}}`.

## Quality vs cost vs latency

- Total LLM requests (all stages, including retries): 700.
- Total embedding requests: 14.
- Total accumulated embedding API time: 1.773 seconds.
- Accumulated LLM API time A / B: 4871.132 / 8667.619 seconds.
- B extraction added 100 LLM requests and 3904.24 seconds over A's generation path.
- Additional total B LLM requests vs A, including validation: -100.
- Request-count comparison is affected by retries: A generation recorded more than one HTTP attempt per tool, while B generation recorded one. The response status for each attempt was not persisted, so the excess attempts cannot be attributed to a specific transient cause from this run.
- Accumulated B LLM time minus A: 3796.488 seconds. This sums per-stage API time; it is not Airflow wall-clock duration.
- Provider token usage and price were not returned; request counts and elapsed time are cost proxies, not monetary estimates.

- Airflow task-run wall times: `{"experiment_id":"23c03cf7-0c4f-425a-b44d-fb16755605f5","limitations":["LLM judge scores are automated and require manual expert review.","Token and monetary usage were not available from the provider response."],"runs":[{"dag_id":"tool_metadata_enrichment","duration_seconds":1569.712797,"end_date":"2026-11-03T01:56:17.342268+00:00","notes":"Task succeeded after infrastructure and authentication corrections; first attempt had missing worker DAG mount and placeholder API credential. Successful outputs were recorded on retry; persisted stage request counts are included in the database report.","run_id":"manual__2026-11-03T01:29:29.786656+00:00","start_date":"2026-11-03T01:30:07.629471+00:00","state":"success","variant":"A"},{"dag_id":"tool_metadata_enrichment","duration_seconds":5083.571842,"end_date":"2026-11-03T03:21:00.959432+00:00","run_id":"manual__variant_B_23c03cf7","start_date":"2026-11-03T01:56:17.387590+00:00","state":"success","variant":"B"},{"dag_id":"tool_metadata_embedding","duration_seconds":4.549615,"end_date":"2026-11-03T01:56:21.883769+00:00","run_id":"asset_triggered__2026-11-03T01:56:17.087415+00:00_4XzV6fJ4","start_date":"2026-11-03T01:56:17.334154+00:00","state":"success","variant":"A"},{"dag_id":"tool_metadata_embedding","duration_seconds":12.079296,"end_date":"2026-11-03T03:21:13.029681+00:00","run_id":"asset_triggered__2026-11-03T03:20:59.988684+00:00_Yv49hZYU","start_date":"2026-11-03T03:21:00.950385+00:00","state":"success","variant":"B"},{"dag_id":"tool_metadata_validation","duration_seconds":3470.135481,"end_date":"2026-11-03T03:00:44.794299+00:00","run_id":"manual__validation_A_23c03cf7","start_date":"2026-11-03T02:02:54.658818+00:00","state":"success","variant":"A"},{"dag_id":"tool_metadata_validation","duration_seconds":3588.952239,"end_date":"2026-11-03T04:21:47.636827+00:00","run_id":"manual__validation_B_23c03cf7","start_date":"2026-11-03T03:21:58.684588+00:00","state":"success","variant":"B"}],"sample":{"sha256":"f22fd8dfe61e4a01584a546ad443adaeec7cd1e57a682f6f7212ddb80383d98f","size":100},"timezone":"UTC"}`.
- API token usage and monetary pricing were not returned by the service; request count and measured latency are the available cost proxies.

## Human review

No human ratings are prefilled. `manual_review.csv` provides one review row per tool with reviewer, A/B judgment, scores, and notes. `report.html` provides a side-by-side viewer and exports completed browser-local judgments to CSV. Automatic and LLM-based judgments remain clearly separate from human ratings.

## Failures and limitations

- Failed enrichment rows: A=0, B=0; see `comparison.jsonl` for per-tool failure stage and error.
- The sample is intentionally source-balanced relative to ToolDB's BioTools-heavy distribution and is not a prevalence-weighted estimate for the full database.
- LLM-as-judge scores can share model biases and are not independent ground truth.
- Embedding similarity indicates semantic closeness only.
- Monetary API cost is unknown without provider token-usage and pricing data.

## Reproducibility

The checked-in `representative_sample_100.json` contains the fixed UUIDs and SHA-256. Trigger `tool_metadata_enrichment` twice with the same `experiment_id`, first with `variant: A`, then `variant: B`, and the same `sample_path`. Trigger `tool_metadata_validation` independently for each variant. The enrichment Asset schedules `tool_metadata_embedding` automatically. Re-running a completed variant with unchanged source hashes is idempotent; changed source inputs require a new experiment ID.

## Conclusion

- The LLM judge rated descriptions 4.61/5 for A and 4.55/5 for B; paired directions were `{"A_better":27,"B_better":21,"both_poor":0,"similar":52}`.
- Mean embedding cosine similarity was 0.9694, which indicates that the descriptions are semantically close but does not establish factual quality.
- On this sample and judge, B did not show a clear description-quality gain over A and required more measured LLM time (4871.132 seconds for A vs 8667.619 seconds for B). Treat this as a preliminary result: the judge uses the same model family as generation and manual expert ratings are still pending.
- Review the side-by-side HTML and `manual_review.csv` before deciding whether extraction's additional signal justifies its latency. Request totals are confounded by A's higher recorded generation retry count, whose per-attempt response status was not retained.
