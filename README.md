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
