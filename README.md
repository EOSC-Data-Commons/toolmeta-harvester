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

## Semantic enrichment experiment (A/B)

This experiment checks whether a structured semantic extraction step improves
short, factual tool descriptions for discovery and tool–dataset matching. It
uses the existing ToolDB and keeps generated data in dedicated tables; it does
not change harvested source metadata.

### Pipeline

- **Sample:** `scripts/create_experiment_sample.py` creates and persists one
  stratified 100-tool sample (70 BioTools records and 30 sampled across other
  sources). The JSON records the IDs, strata, source counts, and a checksum.
  Both variants must use this exact file; the pipeline verifies its checksum.
- **A:** generates a description directly from normalized and allowlisted raw
  source metadata.
- **B:** extracts a structured semantic profile first, then generates a
  description from the same source metadata plus that profile.
- **Validation:** deterministic checks and an LLM review run independently;
  validation does not block embedding.
- **Embedding:** an Airflow Asset event from enrichment schedules embedding for
  completed descriptions. Each vector points to the exact enrichment row.

`tool_enrichments` stores one row per tool, experiment UUID, and variant.
There is no experiment/run table. Rows preserve extraction, generation and
validation requested/actual model names, prompt versions, input hashes, request
counts, timings, validation results, and failures. The API-reported model is
recorded separately from the configured model; automatic model fallbacks are
disabled so A/B comparisons remain attributable. `tool_embeddings` stores
vectors and their requested/actual model, batch ID, request count and latency.
Source metadata embeddings may still have a NULL `enrichment_id`.

### Configuration and execution

Configuration is loaded from `config/config.toml` and Dynaconf environment
variables prefixed `TOOLMETA_HARVESTER_`. In Airflow, set the corresponding
values in the local warehouse `.env`; keep API keys out of source control and
reports. Model and endpoint settings include:

- `EGI__LLM_API_URL`, `EGI__LLM_API_KEY`, `EGI__LLM_MODEL`
- `EGI__EXTRACTION_MODEL`, `EGI__GENERATION_MODEL`, `EGI__VALIDATION_MODEL`
- `EGI__LLM_TIMEOUT`, `EGI__LLM_MAX_RETRIES`
- `EGI__EMBEDDING_API`, `EGI__EMBEDDING_MODEL`

The API client uses the configured model without a fallback. Transient request
retries are counted and included in the result provenance. Check `config.toml`
for the defaults. Apply schema updates with `alembic upgrade head`.

Three local Airflow DAGs handle the stages:

- `tool_metadata_enrichment` takes `experiment_id`, `variant` (`A` or `B`),
  and optional `sample_path` in its run configuration. It emits the enriched
  description Asset after successful completion.
- `tool_metadata_embedding` runs when that Asset is updated and embeds all
  completed enrichment rows missing a vector, whether or not validation ran.
- `tool_metadata_validation` takes the same experiment, variant, and sample
  configuration and is independent from embedding.

For reproducibility, trigger A and B with the same UUID and sample path. A
persisted record can be inspected with
[`reports/enrichment_manual_review.sql`](reports/enrichment_manual_review.sql):
replace the placeholder UUID in `selected_experiment`. The query joins the raw
source attributes, extraction output, both descriptions, validation,
per-stage model and prompt provenance, metrics, and embedding similarity.

Generate comparison and expert-review artifacts from the completed database
results with:

```sh
PYTHONPATH=src python scripts/generate_experiment_report.py \
  --experiment-id <UUID> \
  --sample-path experiments/<experiment>/representative_sample_100.json \
  --output-dir experiments/<experiment>
```

The report directory contains summary metrics, JSONL records, a side-by-side
CSV for expert review, an HTML comparison page, and an experiment narrative.
LLM scores are useful signals, not ground truth. Human review remains needed
before treating the descriptions as authoritative. The API may not report
usage or price; in that case the report provides request counts and latency as
observable cost proxies.
