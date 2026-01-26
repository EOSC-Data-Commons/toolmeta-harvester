.PHONY: run-local
run-local:
	uv run src/toolmeta_harvester/main.py

.PHONY: sync
sync:
	uv sync
	uv pip install -e .

