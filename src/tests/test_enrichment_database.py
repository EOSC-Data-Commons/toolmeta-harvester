"""PostgreSQL persistence checks for paired, result-linked enrichment records."""

from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.orm import Session

from toolmeta_harvester.db.models import ToolEmbedding, ToolEnrichment, ToolMetadata

DATABASE_URL = os.environ.get("TOOLMETA_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not DATABASE_URL,
    reason="set TOOLMETA_TEST_DATABASE_URL to enable PostgreSQL persistence checks",
)


def test_a_and_b_can_coexist_for_one_tool_and_embeddings_link_to_each_result():
    engine = create_engine(DATABASE_URL)
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    assert {"tool_enrichments", "tool_embeddings"} <= tables
    assert "tool_enrichment_runs" not in tables
    metadata_columns = {
        column["name"] for column in inspector.get_columns("tool_metadata")
    }
    assert "enriched_description" not in metadata_columns
    assert "enrichment_status" not in metadata_columns
    enrichment_columns = {
        column["name"] for column in inspector.get_columns("tool_enrichments")
    }
    assert {
        "tool_id",
        "experiment_id",
        "variant",
        "extraction_used",
        "extraction_result",
        "enriched_description",
        "model",
        "prompt_version",
        "validation",
        "input_hash",
        "source_hash",
        "extraction_request_count",
        "generation_elapsed_seconds",
    } <= enrichment_columns
    assert "enrichment_id" in {
        column["name"] for column in inspector.get_columns("tool_embeddings")
    }

    tool_id = uuid.uuid4()
    experiment_id = uuid.uuid4()
    try:
        with Session(engine) as session:
            tool = ToolMetadata(
                id=tool_id,
                metadata_format="persistence-test",
                raw_metadata={},
                title="Paired enrichment persistence test",
            )
            session.add(tool)
            # Flush the source row first: this table has database triggers and
            # keeping the fixture's insert order explicit avoids relying on
            # mapper dependency ordering for an unrelated integration test.
            session.flush()
            baseline = ToolEnrichment(
                tool_id=tool_id,
                experiment_id=experiment_id,
                variant="A",
                extraction_used=False,
                status="completed",
                enriched_description="Baseline description",
                requested_model="requested-model",
                model="actual-model",
                prompt_version="generation_v1",
                input_hash="a" * 64,
                validation_status="completed",
                validation={"accuracy_score": 4},
            )
            extracted = ToolEnrichment(
                tool_id=tool_id,
                experiment_id=experiment_id,
                variant="B",
                extraction_used=True,
                status="completed",
                extraction_result={"supported_tasks": ["classification"]},
                enriched_description="Extraction-assisted description",
                requested_extraction_model="extractor",
                extraction_model="actual-extractor",
                requested_model="requested-model",
                model="actual-model",
                prompt_version="generation_v1",
                input_hash="b" * 64,
                validation_status="completed",
                validation={"accuracy_score": 5},
            )
            session.add_all([baseline, extracted])
            session.flush()
            session.add_all(
                [
                    ToolEmbedding(
                        tool_id=tool_id,
                        enrichment_id=baseline.id,
                        embedding_type="enriched_description",
                        embedding_model="nomic-embed-text-v2-moe",
                        actual_model="nomic-embed-text-v2-moe",
                        text=baseline.enriched_description,
                        vector=[0.1] * 768,
                    ),
                    ToolEmbedding(
                        tool_id=tool_id,
                        enrichment_id=extracted.id,
                        embedding_type="enriched_description",
                        embedding_model="nomic-embed-text-v2-moe",
                        actual_model="nomic-embed-text-v2-moe",
                        text=extracted.enriched_description,
                        vector=[0.2] * 768,
                    ),
                ]
            )
            session.commit()

        with Session(engine) as session:
            rows = session.scalars(
                select(ToolEnrichment)
                .where(
                    ToolEnrichment.tool_id == tool_id,
                    ToolEnrichment.experiment_id == experiment_id,
                )
                .order_by(ToolEnrichment.variant)
            ).all()
            assert [row.variant for row in rows] == ["A", "B"]
            assert rows[0].extraction_used is False
            assert rows[1].extraction_used is True
            assert rows[1].extraction_model == "actual-extractor"
            vectors = session.scalars(
                select(ToolEmbedding).where(ToolEmbedding.tool_id == tool_id)
            ).all()
            assert {row.enrichment_id for row in vectors} == {row.id for row in rows}
    finally:
        with Session(engine) as session:
            session.query(ToolEmbedding).filter_by(tool_id=tool_id).delete()
            session.query(ToolEnrichment).filter_by(tool_id=tool_id).delete()
            session.query(ToolMetadata).filter_by(id=tool_id).delete()
            session.commit()
        engine.dispose()
