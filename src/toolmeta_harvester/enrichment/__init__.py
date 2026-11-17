"""Production enrichment API and its optional validation and embedding operations."""

from importlib import import_module
from typing import Any

__all__ = [
    "embed_enrichment_batch",
    "processing_report",
    "run_enrichment",
    "run_validation",
    "select_enrichment_batches",
    "select_pending_embedding_batches",
]


def __getattr__(name: str) -> Any:
    if name not in __all__:
        raise AttributeError(name)
    return getattr(import_module("toolmeta_harvester.enrichment.pipeline"), name)
