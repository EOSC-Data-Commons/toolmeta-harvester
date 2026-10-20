"""Opt-in persistence smoke test for the experiment-aware enrichment schema."""

from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session

from toolmeta_harvester.db.models import ToolEnrichment, ToolEnrichmentRun, ToolMetadata

DATABASE_URL = os.environ.get("TOOLMETA_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="set TOOLMETA_TEST_DATABASE_URL to enable PostgreSQL persistence test",
)


def test_enrichment_results_and_actual_models_persist_separately():
    engine = create_engine(DATABASE_URL)
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    assert {"tool_enrichment_runs", "tool_enrichments", "tool_embeddings"} <= tables
    assert "enrichment_status" not in {
        column["name"] for column in inspector.get_columns("tool_metadata")
    }
    enrichment_columns = {
        column["name"] for column in inspector.get_columns("tool_enrichments")
    }
    assert {
        "tool_id",
        "run_id",
        "status",
        "enriched_description",
        "extraction_model",
        "generation_model",
        "validation_model",
        "validation",
    } <= enrichment_columns
    assert "enrichment_id" in {
        column["name"] for column in inspector.get_columns("tool_embeddings")
    }

    tool_id, run_id = uuid.uuid4(), uuid.uuid4()
    try:
        with Session(engine) as session:
            session.add(
                ToolMetadata(
                    id=tool_id,
                    metadata_format="test",
                    raw_metadata={},
                    title="Persistence test",
                )
            )
            session.add(
                ToolEnrichmentRun(
                    id=run_id,
                    name="persistence-test",
                    status="completed",
                    requested_extraction_model="test-requested",
                    requested_generation_model="test-requested",
                    requested_validation_model="test-requested",
                    extraction_prompt_version="extraction_v1",
                    generation_prompt_version="generation_v1",
                    validation_prompt_version="validation_v1",
                    sample_size=1,
                )
            )
            session.flush()
            session.add(
                ToolEnrichment(
                    tool_id=tool_id,
                    run_id=run_id,
                    status="validated",
                    enriched_description="Temporary test enrichment",
                    extraction_model="test-actual-extraction",
                    generation_model="test-actual-generation",
                    validation_model="test-actual-validation",
                    validation={"accuracy_score": 5},
                )
            )
            session.commit()
        with Session(engine) as session:
            saved = session.query(ToolEnrichment).filter_by(tool_id=tool_id).one()
            assert saved.enriched_description == "Temporary test enrichment"
            assert saved.extraction_model == "test-actual-extraction"
            session.delete(session.get(ToolMetadata, tool_id))
            session.delete(session.get(ToolEnrichmentRun, run_id))
            session.commit()
    finally:
        with Session(engine) as session:
            session.query(ToolMetadata).filter_by(id=tool_id).delete()
            session.query(ToolEnrichmentRun).filter_by(id=run_id).delete()
            session.commit()
        engine.dispose()
