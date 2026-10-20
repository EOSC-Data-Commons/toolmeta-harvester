"""Opt-in persistence smoke test for a migrated local PostgreSQL database."""

from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session

from toolmeta_harvester.db.models import ToolMetadata

DATABASE_URL = os.environ.get("TOOLMETA_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="set TOOLMETA_TEST_DATABASE_URL to enable PostgreSQL persistence test",
)


def test_enrichment_columns_persist_and_model_matches_schema():
    engine = create_engine(DATABASE_URL)
    inspector = inspect(engine)
    columns = {column["name"] for column in inspector.get_columns("tool_metadata")}
    expected = {
        "input_description",
        "output_description",
        "semantic_metadata",
        "enriched_description",
        "enrichment_status",
        "enrichment_input_hash",
        "enrichment_version",
        "enrichment_error",
        "enrichment_failed_stage",
        "enrichment_validation",
        "enriched_at",
    }
    assert expected <= columns
    assert "tool_embeddings" in inspector.get_table_names()
    embedding_columns = {
        column["name"] for column in inspector.get_columns("tool_embeddings")
    }
    assert {
        "tool_id",
        "embedding_type",
        "embedding_model",
        "text",
        "vector",
    } <= embedding_columns

    record_id = uuid.uuid4()
    try:
        with Session(engine) as session:
            record = ToolMetadata(
                id=record_id,
                metadata_format="test",
                raw_metadata={},
                title="Persistence test tool",
                input_description="Test input description",
                output_description="Test output description",
                semantic_metadata={"supported_tasks": ["test"]},
                enriched_description="Temporary test enrichment",
                enrichment_status="validated",
                enrichment_input_hash="0" * 64,
                enrichment_version="test_v1",
                enrichment_validation={"accuracy_score": 5},
            )
            session.add(record)
            session.commit()
        with Session(engine) as session:
            saved = session.get(ToolMetadata, record_id)
            assert saved is not None
            assert saved.enriched_description == "Temporary test enrichment"
            assert saved.semantic_metadata == {"supported_tasks": ["test"]}
            session.delete(saved)
            session.commit()
    finally:
        with Session(engine) as session:
            saved = session.get(ToolMetadata, record_id)
            if saved is not None:
                session.delete(saved)
                session.commit()
        engine.dispose()
