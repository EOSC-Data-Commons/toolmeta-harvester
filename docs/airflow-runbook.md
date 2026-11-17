# Tool metadata enrichment runbook

## Components and responsibilities

- `tool_metadata_enrichment` is manually triggered. It selects records, maps them into batches of 10, and invokes one generation request per eligible record. Airflow limits the DAG to four active tasks and one active run.
- `tool_metadata_embedding` consumes one Asset event after all enrichment batches finish, then maps all successful current results missing vectors into batches of 10.
- `tool_metadata_validation` is a separate manual LLM review. It stores findings separately and cannot edit generation results.
- `tool_metadata_processing_report` reads persisted attempts and produces business-level counts without calling an LLM.
- ToolDB stores source metadata, append-only generation attempts, optional validation results, and description vectors in separate tables.

## Configuration

The host-side package reads `.env` using Dynaconf, then allows `TOOLMETA_HARVESTER_*` environment variables to override it. For database access from the host, use `localhost` and the published PostgreSQL port. In Airflow containers, use the Docker service hostname and database credentials injected by the `metadata-warehouse` Compose environment. The running local Airflow stack reads the sibling repository's `.env`; do not copy credentials into Git or DAG files.

Required enrichment settings are the ToolDB host, port, name, user and password, plus `TOOLMETA_HARVESTER_EGI__LLM_API_KEY`. The default chat endpoint is `https://llm.ai.egi.eu/v1/chat/completions`, generation model is `qwen3.8-27b`, and prompt identity is recorded in the database. Embedding uses the configured embedding endpoint/model and the same EGI API key. See `.env.example` for the complete variable list.

There is no model fallback. The requested model and provider-returned model are stored separately. This keeps model comparisons attributable and prevents a silent fallback from being recorded as the requested model.

## Local Airflow development

Run from the `metadata-warehouse` checkout. This command uses the local source bind mounts in `docker-compose.dev.yml`; it preserves all named volumes and does not remove data:

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml -f docker-compose.override.yml \
  up -d --no-deps airflow-api-server airflow-scheduler airflow-dag-processor airflow-worker
```

The API server is exposed on `http://localhost:8081` in this Compose setup. Check DAG import errors before triggering a run. For a routine local development change, the bind mount makes new DAG/package files visible without rebuilding the Airflow image. If a dependency changes, rebuild the Airflow image with the same project ref before testing.

## Migration ordering

1. Confirm the target is the intended local or staging ToolDB and inspect `alembic current`.
2. Install the exact application/DAG revision that contains the migration.
3. Run `uv sync --frozen` (or build the corresponding Airflow image).
4. Run `uv run alembic upgrade head` from this repository with that environment's database settings.
5. Verify the revision and the three additive tables: `tool_metadata_enrichment`, `tool_metadata_enrichment_validation`, and `tool_metadata_enrichment_embedding`.
6. Deploy/activate the DAG only after migration verification.

For a clean local database, initialize ordinary harvesting tables first, then run the Alembic upgrade. `initialize_db()` is not the enrichment migration mechanism. The migration retains the historical A/B tables and source metadata. Downgrade intentionally does not delete enrichment history. Do not apply migrations to production as part of this PR. Staging/production deployment must follow the same migration order after review and a staging rehearsal.

## Triggering enrichment

Use Airflow's manual trigger form with one of these JSON objects:

```json
{"limit": 100}
```

```json
{"tool_ids": ["uuid-1", "uuid-2"]}
```

```json
{"full_catalog": true}
```

The default is bounded to 100 records. `tool_ids` cannot be combined with `limit` or `full_catalog`. A full-catalog run must be explicitly selected and cannot include `limit`. Before an approximately 50,000-record run, estimate service quota and elapsed time from a small pilot, check failure/retry rates, confirm the embedding service is available, and coordinate the maintenance window. The selection task emits 5,000 generation batches at 10 records for a 50k catalogue; the embedding backfill maps eligible vectors in the same batch size. Airflow caps active tasks and the local Compose environment allows up to 10,000 mapped tasks. Each worker commits each record's attempt before/after the remote call, so a retry of a batch reuses matching successful or insufficient results.

No fallback model is configured. Transient HTTP 408/429/5xx and transport errors use bounded exponential backoff with jitter. Permanent HTTP errors stop retrying. Empty/malformed JSON and schema-invalid responses are retried within the configured limit. Errors stored in ToolDB contain sanitized categories, not provider response bodies or credentials.

## Statuses and reruns

| Status | Meaning | Request made? | Description stored? |
| --- | --- | ---: | ---: |
| `generated` | Valid, non-empty generation response persisted. | Yes | Yes |
| `insufficient_metadata` | Model could not support a reliable description. | Yes | No |
| `skipped_empty_metadata` | `raw_metadata` is null/empty. | No | No |
| `failed` | API, response validation, or processing failure after bounded retries. | Usually | No |
| `up_to_date` | Matching input hash, requested model and prompt identity already have a terminal result. | No | No new description |
| `skipped_inflight` | A concurrent run is already processing this tool. | No | No |
| `processing` | A persisted attempt is currently in progress. | In progress | No |

Failed attempts do not overwrite an earlier successful attempt. Rerun the failed tool IDs using `tool_ids`; completed rows are idempotently skipped. A `processing` attempt older than 30 minutes is marked failed under the per-tool lock and made eligible for retry; the normal LLM timeouts and retry bounds are shorter than that lease.

## Review and reporting

Trigger `tool_metadata_processing_report` with `{"run_id": "<enrichment DAG run id>"}` or a period such as `{"since":"2026-11-15T00:00:00+00:00","until":"2026-11-16T00:00:00+00:00"}`. With no parameters it reports the previous 24 hours. The report includes status counts, failed tool IDs, requests, retries, timings and throughput. The report DAG makes no API calls. Use the SQL query in the README for manual field-expert review of source payload, generated text, provenance, validation and vectors together.

The LLM validation DAG accepts `tool_ids`, `enrichment_ids`, or `limit` up to 1000. Validation is advisory, stored separately, and is never a gate for generation or embeddings.

## 50k capacity and monitoring notes

The code bounds database reads and Airflow work items; it does not claim that a 50k production run has been benchmarked. The current local DB contains approximately 37.5k tool rows. The implementation review should measure average request latency, provider rate limits, retry distribution, error fraction and embedding throughput on a small local pilot before any staging scale run. At four parallel Airflow tasks and 10 records per task, each task is sequential within its batch; adjust DAG concurrency only after confirming EGI and database capacity. Keep the run ID for correlation across individual rows and the report DAG.

Staging and production have not been migrated or exercised by this local runbook work. Do not infer production readiness from unit tests or the local pilot alone.
