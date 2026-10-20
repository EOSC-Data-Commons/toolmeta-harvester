# Tool metadata enrichment audit

This read-only audit was completed before schema or application changes. The
database figures below were queried from the local PostgreSQL `tooldb` on
2026-10-19. No secrets or credentials are included.

## Architecture and current integrations

- `toolmeta-harvester` stores harvested records in PostgreSQL through SQLAlchemy
  and Alembic. Harvesting is organized in Python flows and invoked through thin
  Airflow DAGs.
- `ToolMetadata` stores normalized fields plus source-preserving `raw_metadata`
  JSONB. `ToolEmbedding` is defined in the ORM with a 768-dimensional pgvector,
  and an existing Airflow task embeds descriptions through EGI. In the live
  development database there was no `tool_embeddings` table, vector extension,
  or embedding row.
- The sibling `metadata-warehouse` project supplies the local Airflow 3.3.2
  Celery stack and mounts the harvester checkout into the Airflow containers.
- The repository had no chat-completion client or enrichment stages. Existing
  LLM-related code was limited to the embedding endpoint.
- The database was at Alembic revision `7fff94b25184`, absent from this checkout.
  Its `tool_metadata` columns and source uniqueness constraint matched the
  checked-in schema through `0d26b79ee97b`, so a documented no-op bridge was
  added before the enrichment migration.

## Database statistics

There were **37,494** `tool_metadata` rows.

| Field | Populated rows | Coverage |
| --- | ---: | ---: |
| title | 37,494 | 100.00% |
| description | 37,468 | 99.93% |
| raw_description | 37,468 | 99.93% |
| keywords | 35,374 | 94.35% |
| types | 37,493 | 100.00% |
| software_types | 30,188 | 80.51% |
| consumes_data | 4,113 | 10.97% |
| produces_data | 3,409 | 9.09% |
| inputs | 4,927 | 13.14% |
| outputs | 4,148 | 11.06% |
| raw_metadata | 37,494 | 100.00% |

The source mix was:

| Metadata format | Rows | Share |
| --- | ---: | ---: |
| BioTools | 34,445 | 91.87% |
| WorkflowHub JSON | 1,584 | 4.22% |
| CodeMeta | 1,411 | 3.76% |
| Boutiques | 37 | 0.10% |
| RO-Crate | 16 | 0.04% |
| JSON-LD | 1 | <0.01% |

Description lengths had a median of 186 characters and p95 of 835. Raw
description lengths had a median of 186 and p95 of 897. `raw_metadata` JSONB
storage had a mean of about 2,147 bytes, median 2,098 bytes, and p95 3,310
bytes. It is small enough to inspect selectively, but sending it wholesale
would include unrelated provenance and access details.

Of 12,088 input entries, 2,435 (20.1%) had a non-empty description. Of 13,203
output entries, 902 (6.8%) had one. Records often have no input/output arrays
at all. Examples with detailed parameter semantics include Boutiques tools
such as `Bruker-preproc` and `ct-tiqua`; examples with no normalized input or
output declarations include BioTools entries such as `P2Rank` and `POMS`.

## Raw metadata findings

The most frequent BioTools raw keys include `name` and `description` (35,894
records each), `license` (35,857), `version` and `operatingSystem` (34,446),
and `function`, `topic`, `documentation`, and `publication` (34,445). For
example, P2Rank has raw `function.operation` terms for protein binding site
prediction and raw topic terms for protein features, cheminformatics,
structural biology, and protein interactions. POMS has operations and topics
for phylogenetic inference, enrichment analysis, microbiome studies, and
metagenomics. Those terms add useful semantic information not represented by
its normalized input/output arrays.

WorkflowHub raw records wrap workflow attributes below `data.attributes` and
can include many input/output ports and workflow steps. Boutiques raw records
retain parameter names, descriptions, defaults, and file patterns. CodeMeta
records may be sparse: a sample `CitRe` record had a 316-byte JSONB payload and
no normalized inputs or outputs. Raw metadata is therefore source-dependent.

## Data quality and design decisions

- Titles and descriptions are consistently available; descriptions vary in
  detail. Keywords and software types often add context.
- Input/output declarations, consumes/produces metadata, and especially output
  descriptions are sparse. A bare `File` type is insufficient to infer a
  scientific file format or meaning.
- BioTools dominates the current data. A representative sample of this
  database will not establish generality across sources.
- Extraction input should include normalized title, both descriptions,
  keywords, types, software types, consumes/produces data, inputs, outputs,
  and a small allowlisted semantic subset from `raw_metadata` (`topic`,
  `function`, `operation`, inputs/outputs, workflow steps, and data types).
  Source IDs, owners, timestamps, URLs, and other operational fields should
  stay out of the prompt and input hash.
- Enrichment fields are added to `tool_metadata` so their hash, status, prompt
  version, failure reason, validation result, and generated description stay
  associated with the source record. `ToolEmbedding` is kept separate.
- Four manually triggered DAGs separate extraction, generation, validation,
  and embeddings. The deterministic first sample reserves one record per source
  where possible, then allocates the remaining slots by source share. The
  100-record allocation is 87 BioTools, 5 WorkflowHub, 5 CodeMeta, and one
  record from each smaller source.

## Risks and limitations

- An LLM can still make unsupported inferences. Extraction prompts, schema
  validation, and a second model review reduce risk but do not establish truth.
- The validation model scores are advisory. Manual review is required.
- Sparse records will legitimately retain empty input/output descriptions and
  semantic lists.
- The LLM endpoint may have availability or latency limits; failures are stored
  per stage and can be retried without redoing completed stages.
- The 100-record experiment is a feasibility sample, not a retrieval-quality
  evaluation. No retrieval metrics are included.
