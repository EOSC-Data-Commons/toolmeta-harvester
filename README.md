> 🚧 Work in Progress  
> This project is currently under active development.  
> Features may change, and the API may not be stable yet.  
> Contributions and feedback are welcome!

# Roadmap

## 🚧 Phase 1 — Foundation Galaxy focused (Current)

- [x] Project scaffolding and initial architecture
- [x] Interface to Galaxy ToolShed API
- [x] Interface to WorkflowHub API
- [x] Parsing Galaxy workflows and enrich with ToolShed data
- [x] Data models for Galaxy tools and workflows
- [x] Generalized data model for artifacts and contracts
- [x] Initial data harvesting and storage from WorkflowHub

## 🚧 Phase 2 — Expansion and Refinement
- [x] Refactor flows to be compatabile with Airflow DAGs
- [x] Refactor flows to be incrimental and idempotent
- [ ] Additional harvest pipelines HAL
- [x] Additional harvest pipelines bio.tools
- [ ] Additional harvest pipelines Containers
- [x] Add single source URL harvest for workflowhub.eu
- [x] Add single source URL harvest for bio.tools
- [x] Add single source URL harvest for github.com
- [x] Add single source URL harvest for zenodo.org
- [x] Add single source URL harvest for gitlab.* instances
- [ ] Create initial embedding pipeline

# Installation and Usage

## Prerequisites

- Python 3.12+
- Docker
- uv

## Credentials

Setup `config/.secrets.toml` with Github API token

## Setup

```
make install
```

Boots Postgres Docker container and installs dependencies

```
make run
```

Runs a default pipeline that harvests data from WorkflowHub, stores it in the db.

## Semantic enrichment experiment (prototype)

### Goal and audit

This prototype evaluates whether existing tool metadata can support a richer,
factual semantic representation for scientific tool discovery and future
tool–dataset matching. It does not harvest additional sources or measure
retrieval quality. The database audit is recorded in
[`docs/enrichment-audit.md`](docs/enrichment-audit.md).

The local database contained 37,494 records. BioTools contributed 34,445
(91.87%), so the experiment is source-skewed. Titles and descriptions were
populated on 100% and 99.93% of records; keywords on 94.35%; software types on
80.51%. Inputs and outputs were present on 13.14% and 11.06% of records, and
`consumes_data` / `produces_data` on 10.97% / 9.09%. Input descriptions were
present for 20.1% of input entries; output descriptions for 6.8% of output
entries. Raw metadata was present on every record, with median/p95 JSONB sizes
of about 2.1/3.3 KB. BioTools `function.operation` and `topic` entries and
source-specific workflow or parameter details provide useful semantics that
are not always present in normalized input/output columns.

### Architecture and data model

The harvester remains the source of truth. The pipeline uses the existing
PostgreSQL database, SQLAlchemy models, Alembic migrations, and Airflow
orchestration. Its stages live in `src/toolmeta_harvester/enrichment/`:

1. **Extraction** converts focused source metadata into validated structured
   fields: input/output descriptions, supported tasks, methods and techniques,
   and scientific domains.
2. **Generation** writes a concise `enriched_description` grounded in the
   source fields and extraction result.
3. **Validation** checks the generated result with deterministic schema checks
   and a separate LLM review. Scores range from 0 (unsupported/unusable) to 5
   (strongly supported/useful); they are advisory, not ground truth.
4. **Embedding** embeds validated `enriched_description` text in the existing
   768-dimensional `ToolEmbedding` store and links each vector to its
   enrichment result.

Enrichment data is kept out of `tool_metadata`. `tool_enrichment_runs` stores
the requested model and prompt version for each stage plus the experiment
status. `tool_enrichments` stores each tool's extracted fields, enriched
description, validation, input hash, and the model name reported by the API for
each stage. The `(tool_id, run_id)` key allows multiple model/prompt runs to be
compared without overwriting earlier results. Embeddings link to one specific
enrichment row, so they remain comparable too. If an API response omits its
model name, the actual-model column stays NULL; the requested model remains
available on the run. Fallback models are disabled so a request cannot silently
switch models without provenance.

The input hash covers only the fields sent to extraction. Statuses include
`pending`, `processing`, `extracted`, `generated`, `validated`, and `failed`;
retries within a run resume at the failed stage. Prompt versions such as
`extraction_v1` are stored separately from the requested and API-reported model
names.

The local database was already stamped at revision `7fff94b25184`, which was
not included in this checkout. The added no-op bridge records the inspected
schema baseline. Migration `a13c45ee79d1` moves prior enrichment data into a
legacy run and creates the experiment-aware tables. Legacy model response names
were not stored and remain NULL; the configured model is retained as requested
model provenance. The migration also links embeddings to a specific enrichment
and preserves source metadata.

### Prompts, configuration, and operation

Prompts are versioned under `src/toolmeta_harvester/enrichment/prompts/`:
`extraction_v1`, `generation_v1`, and `validation_v1`. Their identifiers are
stored with each enrichment result. The extraction prompt explicitly leaves
unknowns empty and tells the model not to infer scientific meaning from a
generic `File` type. Raw metadata is pruned to an allowlist of semantic keys;
IDs, owners, timestamps, links, and unrelated operational fields are excluded.

Configure the EGI chat client with environment variables:

| Variable | Default / purpose |
| --- | --- |
| `LLM_EGI_API_URL` | `https://llm.ai.egi.eu/v1/chat/completions` |
| `LLM_EGI_API_KEY` | Required secret; do not commit or log it |
| `LLM_EGI_MODEL` | `qwen3.8-27b` |
| `LLM_EGI_EXTRACTION_MODEL` | Optional stage override; defaults to `LLM_EGI_MODEL` |
| `LLM_EGI_GENERATION_MODEL` | Optional stage override; defaults to `LLM_EGI_MODEL` |
| `LLM_EGI_VALIDATION_MODEL` | Optional stage override; defaults to `LLM_EGI_MODEL` |
| `LLM_EGI_TIMEOUT` | 180 seconds per request |
| `LLM_EGI_MAX_RETRIES` | 3 retries for transient failures |

For a local CLI run, configure the database connection through
`TOOLMETA_HARVESTER_DATABASE__HOST`, `...__PORT`, `...__NAME`, `...__USER`,
and `...__PASSWORD` as needed. The local Airflow development override forwards
the sibling warehouse's database settings to the default worker and passes
through the LLM environment variables. Set `LLM_EGI_API_KEY` in the local
`metadata-warehouse/.env` before triggering the DAGs.

The Airflow image uses Python 3.13 while the harvester uses Python 3.12. The
DAGs therefore dispatch the enrichment CLI in the dedicated harvester virtual
environment. The warehouse Airflow Dockerfile installs Pydantic v2 into that
environment; rebuild the Airflow image and recreate the default worker after
updating the Dockerfile or local `.env`:

```sh
cd ../metadata-warehouse
docker compose -f docker-compose.yml -f docker-compose.dev.yml build airflow-init
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --force-recreate airflow-worker
```

Run the deterministic 100-record experiment from the repository root:

```sh
uv sync --group dev
PYTHONPATH=src uv run alembic upgrade head
PYTHONPATH=src uv run python -m toolmeta_harvester.enrichment.experiment \
  --stage all --with-embeddings
```

The command prints a `run_id`; pass it with `--run-id` when running a later
single stage. Extraction creates a run automatically when no ID is supplied.
Generation, validation, and embedding require the run ID so they cannot mix
results from different experiments.

The sample reserves one record per available metadata source, then allocates
the remaining slots proportionally. For the audited database that produces
87 BioTools, 5 WorkflowHub, 5 CodeMeta, and one record from each of Boutiques,
RO-Crate, and JSON-LD. Ordering within each source is based on a stable hash of
the record ID. The resulting manual review export contains actual per-stage
model names. The review query in
[`reports/enrichment_manual_review.sql`](reports/enrichment_manual_review.sql)
joins source metadata, enriched attributes, run configuration, validation,
model provenance, and the linked vector.

The four manually triggered Airflow DAGs are:

- `tool_metadata_enrichment_extraction`
- `tool_metadata_enrichment_generation`
- `tool_metadata_enrichment_validation`
- `toolmeta_enriched_description_embedding`

For generation, validation, and embedding DAGs, pass `{"run_id": "<UUID>"}`
in the Airflow run configuration. The extraction DAG can create a run and logs
its ID for subsequent stages.

### Experiment outcome and limitations

The implementation checks completed locally: **10 tests passed**, including a
PostgreSQL persistence/model compatibility check; Ruff formatting and lint
checks passed; and Airflow listed all four new DAGs with no import errors for
the new DAG file. Airflow also reported existing import errors in legacy DAGs
that depend on missing environment variables or packages in the main Airflow
Python environment.

The experiment outcome is recorded per run in the database. Use the exported
review JSONL and `reports/enrichment_manual_review.sql` to inspect source
metadata alongside extracted fields, model provenance, validation, and
embeddings. LLM validation is advisory; manual review remains necessary before
treating enriched descriptions as authoritative.
