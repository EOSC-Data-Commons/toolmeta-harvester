TOOL_REGISTRY_DATABASE__HOST=localhost
TOOL_REGISTRY_DATABASE__PORT=5432
TOOL_REGISTRY_DATABASE__NAME=toolsdb
TOOL_REGISTRY_DATABASE__USER=toolsadmin
TOOL_REGISTRY_DATABASE__PASSWORD=yoursecretsecret
TOOL_REGISTRY_GITHUB__API_KEY=your_github_api_key
POSTGRES_CONTAINER=tool-registry-postgres
POSTGRES_VOLUME=tool_registry_pgdata
TOOLS_CONTAINER=ghcr.io/eosc-data-commons/tool-registry:latest

.PHONY: run-local run
run:run-local

run-local: 
	uv run src/main.py

.PHONY: re-install install
re-install: clean sync

install: postgres-up sync

.PHONY: clean
clean:
	uv clean
	rm uv.lock
	rm -rf .venv/lib/python3.12/site-packages/toolmeta_models/

.PHONY: sync
sync:
	uv sync
	uv pip install -e .

.PHONY: postgres-up postgres-down postgres-logs postgres-reset
postgres-up:
	# Use pgvector image which is postgres with pgvector extension pre-installed, which is required for vector search capabilities in the tool registry.
	@echo "Starting Postgres container '$(POSTGRES_CONTAINER)' on port $(TOOL_REGISTRY_DATABASE__PORT)..."
	docker run -d --rm --name $(POSTGRES_CONTAINER) \
	  	-p $(TOOL_REGISTRY_DATABASE__PORT):5432 \
	  	-e POSTGRES_DB=$(TOOL_REGISTRY_DATABASE__NAME) \
	  	-e POSTGRES_USER=$(TOOL_REGISTRY_DATABASE__USER) \
	  	-e POSTGRES_PASSWORD=$(TOOL_REGISTRY_DATABASE__PASSWORD) \
	  	-v $(POSTGRES_VOLUME):/var/lib/postgresql/data \
	  	pgvector/pgvector:0.8.1-pg16-trixie
	  	# postgres:16

postgres-down:
	@echo "Stopping and removing Postgres container '$(POSTGRES_CONTAINER)'..."
	docker stop $(POSTGRES_CONTAINER) || true
	docker rm $(POSTGRES_CONTAINER) || true

postgres-logs:
	docker logs -f $(POSTGRES_CONTAINER)

postgres-reset: postgres-down
	docker volume rm $(POSTGRES_VOLUME) || true

postgres-shell: 
	docker exec -it $(POSTGRES_CONTAINER) psql -U $(TOOL_REGISTRY_DATABASE__USER) -d $(TOOL_REGISTRY_DATABASE__NAME)

tools-build:
	docker build --network=host -t $(TOOLS_CONTAINER) .

.PHONY: tools-up tools-down tools-logs tools-shell
tools-up: tools-down tools-build
	@echo "Starting Tool Registry container..."
	docker run --name tool-registry \
		-p 8000:8000 \
		-e TOOL_REGISTRY_DATABASE__HOST=$(TOOL_REGISTRY_DATABASE__HOST) \
		-e TOOL_REGISTRY_DATABASE__PORT=$(TOOL_REGISTRY_DATABASE__PORT) \
		-e TOOL_REGISTRY_DATABASE__NAME=$(TOOL_REGISTRY_DATABASE__NAME) \
		-e TOOL_REGISTRY_DATABASE__USER=$(TOOL_REGISTRY_DATABASE__USER) \
		-e TOOL_REGISTRY_DATABASE__PASSWORD=$(TOOL_REGISTRY_DATABASE__PASSWORD) \
		-e TOOL_REGISTRY_GITHUB__API_KEY=$(TOOL_REGISTRY_GITHUB__API_KEY) \
		$(TOOLS_CONTAINER)

tools-down:
	@echo "Stopping and removing Tool Registry container..."
	docker stop tool-registry || true
	docker rm tool-registry || true

tools-logs:
	docker logs -f tool-registry

tools-shell:
	docker exec -it tool-registry /bin/sh
