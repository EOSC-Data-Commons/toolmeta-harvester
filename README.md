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
- [ ] Initial data harvesting and storage from WorkflowHub
- [ ] Deployment to Warehouse
- [ ] Basic documentation (README, setup, usage)
- [ ] Basic tests and CI pipeline


```
uv sync
uv pip install -e .
uv run src/toolmeta_harvester/main.py
```
