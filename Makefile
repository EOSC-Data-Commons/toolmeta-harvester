TOOL_REGISTRY_DATABASE__PORT ?= 8432
TOOL_REGISTRY_DATABASE__NAME ?= tooldb
TOOL_REGISTRY_DATABASE__USER ?= harvester
TOOL_REGISTRY_DATABASE__PASSWORD ?= yoursecretsecret

POSTGRES_CONTAINER ?= tool-registry-postgres
POSTGRES_VOLUME ?= tool_registry_pgdata_pg17
POSTGRES_IMAGE ?= timescale/timescaledb-ha:pg17

.PHONY: install sync run postgres-up postgres-down postgres-shell postgres-reset

install: postgres-up sync

sync:
	uv sync

run:
	@echo "Run a flow with: uv run python src/toolmeta_harvester/flows/<flow_name>.py"
	@ls src/toolmeta_harvester/flows/*.py

postgres-up:
	docker run -d --name $(POSTGRES_CONTAINER) \
		-p 127.0.0.1:$(TOOL_REGISTRY_DATABASE__PORT):5432 \
		-e POSTGRES_DB=$(TOOL_REGISTRY_DATABASE__NAME) \
		-e POSTGRES_USER=$(TOOL_REGISTRY_DATABASE__USER) \
		-e POSTGRES_PASSWORD=$(TOOL_REGISTRY_DATABASE__PASSWORD) \
		-v $(POSTGRES_VOLUME):/home/postgres/pgdata/data \
		-v "$(CURDIR)/docker/postgres/init:/docker-entrypoint-initdb.d:ro" \
		$(POSTGRES_IMAGE)

postgres-down:
	-docker rm -f $(POSTGRES_CONTAINER)

postgres-shell:
	docker exec -it $(POSTGRES_CONTAINER) psql \
		-U $(TOOL_REGISTRY_DATABASE__USER) \
		-d $(TOOL_REGISTRY_DATABASE__NAME)

postgres-reset: postgres-down
	docker volume rm $(POSTGRES_VOLUME)
