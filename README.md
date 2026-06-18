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

- [x] Additional harvest pipelines usegalaxy
- [x] Additional harvest pipelines HAL
- [ ] Additional harvest pipelines bio.tools
- [ ] Additional harvest pipelines Containers
- [ ] Create initial embedding pipeline
- [ ] Enrich tool description e.g. notebook description
- [ ] Task manager e.g. Celery or Prefect for scheduling and orchestration
- [ ] Basic tests and CI pipeline
- [ ] Deployment to Warehouse

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
