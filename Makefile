.PHONY: run-local
run-local: postgres
	uv run src/toolmeta_harvester/main.py

postgres:
	docker compose up -d postgres

.PHONY: sync
sync:
	uv sync
	uv pip install -e .

