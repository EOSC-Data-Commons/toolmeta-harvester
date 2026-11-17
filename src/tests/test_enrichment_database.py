from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.orm import Session

from toolmeta_harvester.db.models import ToolMetadata, ToolMetadataEnrichment

DATABASE_URL = os.environ.get("TOOLMETA_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="set TOOLMETA_TEST_DATABASE_URL for PostgreSQL integration checks",
)


def test_production_tables_keep_source_fields_and_enrichment_provenance():
    engine = create_engine(DATABASE_URL)
    try:
        inspector = inspect(engine)
        assert {
            "tool_metadata_enrichment",
            "tool_metadata_enrichment_validation",
            "tool_metadata_enrichment_embedding",
        } <= set(inspector.get_table_names())
        source_columns = {
            item["name"] for item in inspector.get_columns("tool_metadata")
        }
        assert "raw_metadata" in source_columns
        assert "enriched_description" not in source_columns
        enrichment_columns = {
            item["name"] for item in inspector.get_columns("tool_metadata_enrichment")
        }
        assert {
            "tool_id",
            "status",
            "enriched_description",
            "requested_model",
            "actual_model",
            "prompt_id",
            "prompt_version",
            "input_hash",
            "generation_timestamp",
            "run_id",
            "is_ai_generated",
        } <= enrichment_columns

        tool_id = uuid.uuid4()
        outer = engine.connect()
        transaction = outer.begin()
        session = Session(bind=outer)
        try:
            session.add(
                ToolMetadata(
                    id=tool_id,
                    metadata_format="integration-test",
                    raw_metadata={"name": "Rollback fixture"},
                )
            )
            session.flush()
            session.add(
                ToolMetadataEnrichment(
                    tool_id=tool_id,
                    status="generated",
                    enriched_description="A temporary test tool.",
                    is_ai_generated=True,
                    requested_model="requested-test",
                    actual_model="actual-test",
                    prompt_id="test-prompt",
                    prompt_version="1",
                    input_hash="a" * 64,
                )
            )
            session.flush()
            session.add(
                ToolMetadataEnrichment(
                    tool_id=tool_id,
                    status="failed",
                    enriched_description=None,
                    requested_model="requested-test",
                    prompt_id="test-prompt",
                    prompt_version="1",
                    input_hash="b" * 64,
                    error_code="TestFailure",
                )
            )
            session.flush()
            prior = session.scalar(
                select(ToolMetadataEnrichment).where(
                    ToolMetadataEnrichment.tool_id == tool_id,
                    ToolMetadataEnrichment.status == "generated",
                )
            )
            failed = session.scalar(
                select(ToolMetadataEnrichment).where(
                    ToolMetadataEnrichment.tool_id == tool_id,
                    ToolMetadataEnrichment.status == "failed",
                )
            )
            assert prior.enriched_description == "A temporary test tool."
            assert prior.actual_model == "actual-test"
            assert failed.enriched_description is None
        finally:
            session.close()
            transaction.rollback()
            outer.close()
    finally:
        engine.dispose()
