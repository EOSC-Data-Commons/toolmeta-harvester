"""Add append-only production enrichment, validation, and embedding tables.

Revision ID: ea53f4a99f01
Revises: c83b1f95a722
"""

from collections.abc import Sequence

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "ea53f4a99f01"
down_revision: str | Sequence[str] | None = "c83b1f95a722"
branch_labels = None
depends_on = None


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    tables = _tables()
    if "tool_metadata_enrichment" not in tables:
        op.create_table(
            "tool_metadata_enrichment",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column(
                "tool_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("tool_metadata.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("run_id", sa.String(250)),
            sa.Column("status", sa.String(32), nullable=False),
            sa.Column("enriched_description", sa.Text()),
            sa.Column("requested_model", sa.String(200), nullable=False),
            sa.Column("actual_model", sa.String(200)),
            sa.Column("prompt_id", sa.String(100), nullable=False),
            sa.Column("prompt_version", sa.String(50), nullable=False),
            sa.Column("input_hash", sa.String(64), nullable=False),
            sa.Column(
                "generation_timestamp",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column(
                "request_count", sa.Integer(), server_default="0", nullable=False
            ),
            sa.Column("elapsed_seconds", sa.Float()),
            sa.Column("error_code", sa.String(100)),
            sa.Column("error_message", sa.Text()),
            sa.CheckConstraint(
                "status IN ('processing', 'generated', 'insufficient_metadata', 'skipped_empty_metadata', 'failed', 'up_to_date', 'skipped_inflight')",
                name="ck_tool_metadata_enrichment_status",
            ),
            sa.CheckConstraint(
                "(status = 'generated' AND enriched_description IS NOT NULL AND length(trim(enriched_description)) > 0) OR (status <> 'generated' AND enriched_description IS NULL)",
                name="ck_tool_metadata_enrichment_description_status",
            ),
        )
    indexes = {
        item["name"]
        for item in sa.inspect(op.get_bind()).get_indexes("tool_metadata_enrichment")
    }
    if "ix_tool_metadata_enrichment_tool_created" not in indexes:
        op.create_index(
            "ix_tool_metadata_enrichment_tool_created",
            "tool_metadata_enrichment",
            ["tool_id", "generation_timestamp"],
        )
    if "ix_tool_metadata_enrichment_status" not in indexes:
        op.create_index(
            "ix_tool_metadata_enrichment_status", "tool_metadata_enrichment", ["status"]
        )
    if "uq_tool_metadata_enrichment_inflight" not in indexes:
        op.create_index(
            "uq_tool_metadata_enrichment_inflight",
            "tool_metadata_enrichment",
            ["tool_id"],
            unique=True,
            postgresql_where=sa.text("status = 'processing'"),
        )

    tables = _tables()
    if "tool_metadata_enrichment_validation" not in tables:
        op.create_table(
            "tool_metadata_enrichment_validation",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column(
                "enrichment_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("tool_metadata_enrichment.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("requested_model", sa.String(200), nullable=False),
            sa.Column("actual_model", sa.String(200)),
            sa.Column("prompt_id", sa.String(100), nullable=False),
            sa.Column("prompt_version", sa.String(50), nullable=False),
            sa.Column("status", sa.String(24), nullable=False),
            sa.Column("result", postgresql.JSONB()),
            sa.Column("error_message", sa.Text()),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
        )
    if "ix_tool_metadata_enrichment_validation_enrichment" not in {
        item["name"]
        for item in sa.inspect(op.get_bind()).get_indexes(
            "tool_metadata_enrichment_validation"
        )
    }:
        op.create_index(
            "ix_tool_metadata_enrichment_validation_enrichment",
            "tool_metadata_enrichment_validation",
            ["enrichment_id"],
        )

    tables = _tables()
    if "tool_metadata_enrichment_embedding" not in tables:
        op.create_table(
            "tool_metadata_enrichment_embedding",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column(
                "enrichment_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("tool_metadata_enrichment.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "tool_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("tool_metadata.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("embedding_model", sa.String(200), nullable=False),
            sa.Column("actual_model", sa.String(200)),
            sa.Column("text", sa.Text(), nullable=False),
            sa.Column("vector", Vector(768), nullable=False),
            sa.Column(
                "request_count", sa.Integer(), server_default="0", nullable=False
            ),
            sa.Column("elapsed_seconds", sa.Float()),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.UniqueConstraint(
                "enrichment_id",
                "embedding_model",
                name="uq_tool_metadata_enrichment_embedding",
            ),
        )
    if "ix_tool_metadata_enrichment_embedding_vector" not in {
        item["name"]
        for item in sa.inspect(op.get_bind()).get_indexes(
            "tool_metadata_enrichment_embedding"
        )
    }:
        op.create_index(
            "ix_tool_metadata_enrichment_embedding_vector",
            "tool_metadata_enrichment_embedding",
            ["vector"],
            postgresql_using="hnsw",
            postgresql_ops={"vector": "vector_cosine_ops"},
            postgresql_with={"m": 16, "ef_construction": 64},
        )


def downgrade() -> None:
    # Enrichment attempts are historical data. The downgrade intentionally retains
    # the additive tables; removing them would destroy provenance and embeddings.
    pass
