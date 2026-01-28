.PHONY: run-local run
run:run-local

run-local: 
	uv run src/main.py

.PHONY: postgres
postgres:
	docker compose up -d postgres

.PHONY: db-shell
db-shell: postgres
	docker exec -it tool_postgres psql -U harvester -d admin

.PHONY: sync
sync:
	uv sync
	uv pip install -e .

