"""Create one provenance-rich enrichment table and result-linked embeddings.

Revision ID: c83b1f95a722
Revises: 7fff94b25184
"""

from collections.abc import Sequence

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "c83b1f95a722"
down_revision: str | Sequence[str] | None = "7fff94b25184"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # This derived source column was absent from the clean local staging dump,
    # although the current ToolMetadata model and harvesting code require it.
    op.add_column(
        "tool_metadata",
        sa.Column(
            "search_types",
            postgresql.ARRAY(sa.Text()),
            server_default="{}",
            nullable=False,
        ),
    )
    op.create_index(
        "ix_tool_metadata_search_types_gin",
        "tool_metadata",
        ["search_types"],
        postgresql_using="gin",
    )
    op.execute(
        """CREATE OR REPLACE FUNCTION update_tool_search_types()
        RETURNS trigger AS $$
        BEGIN
            SELECT ARRAY(
                SELECT DISTINCT lower(trim(value))
                FROM (
                    SELECT unnest(coalesce(NEW.types, ARRAY[]::text[])) AS value
                    UNION ALL
                    SELECT obj->>'name'
                    FROM jsonb_array_elements(coalesce(NEW.programming_languages, '[]'::jsonb)) AS obj
                    UNION ALL
                    SELECT obj->>'name'
                    FROM jsonb_array_elements(coalesce(NEW.runtime_platforms, '[]'::jsonb)) AS obj
                    UNION ALL
                    SELECT obj->>'name'
                    FROM jsonb_array_elements(coalesce(NEW.software_types, '[]'::jsonb)) AS obj
                ) AS values
                WHERE value IS NOT NULL AND trim(value) <> ''
            ) INTO NEW.search_types;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql"""
    )
    op.execute(
        """CREATE TRIGGER trg_tool_search_types
        BEFORE INSERT OR UPDATE OF types, programming_languages,
            runtime_platforms, software_types
        ON tool_metadata FOR EACH ROW
        EXECUTE FUNCTION update_tool_search_types()"""
    )
    op.execute("UPDATE tool_metadata SET types = types")

    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "tool_enrichments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tool_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("experiment_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("variant", sa.String(length=1), nullable=False),
        sa.Column(
            "extraction_used", sa.Boolean(), server_default=sa.false(), nullable=False
        ),
        sa.Column(
            "status", sa.String(length=20), server_default="pending", nullable=False
        ),
        sa.Column("extraction_result", postgresql.JSONB(), nullable=True),
        sa.Column("enriched_description", sa.Text(), nullable=True),
        sa.Column("source_hash", sa.String(length=64), nullable=True),
        sa.Column("extraction_input_hash", sa.String(length=64), nullable=True),
        sa.Column("input_hash", sa.String(length=64), nullable=True),
        sa.Column("requested_extraction_model", sa.String(length=200), nullable=True),
        sa.Column("extraction_model", sa.String(length=200), nullable=True),
        sa.Column("requested_model", sa.String(length=200), nullable=True),
        sa.Column("model", sa.String(length=200), nullable=True),
        sa.Column("requested_validation_model", sa.String(length=200), nullable=True),
        sa.Column("validation_model", sa.String(length=200), nullable=True),
        sa.Column("extraction_prompt_version", sa.String(length=100), nullable=True),
        sa.Column("prompt_version", sa.String(length=100), nullable=True),
        sa.Column("validation_prompt_version", sa.String(length=100), nullable=True),
        sa.Column("deterministic_validation", postgresql.JSONB(), nullable=True),
        sa.Column("validation", postgresql.JSONB(), nullable=True),
        sa.Column("extraction_validation", postgresql.JSONB(), nullable=True),
        sa.Column(
            "validation_status",
            sa.String(length=20),
            server_default="pending",
            nullable=False,
        ),
        sa.Column(
            "extraction_request_count", sa.Integer(), server_default="0", nullable=False
        ),
        sa.Column(
            "generation_request_count", sa.Integer(), server_default="0", nullable=False
        ),
        sa.Column(
            "validation_request_count", sa.Integer(), server_default="0", nullable=False
        ),
        sa.Column("extraction_elapsed_seconds", sa.Float(), nullable=True),
        sa.Column("generation_elapsed_seconds", sa.Float(), nullable=True),
        sa.Column("validation_elapsed_seconds", sa.Float(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("failed_stage", sa.String(length=20), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["tool_id"], ["tool_metadata.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tool_id", "experiment_id", "variant", name="uq_tool_enrichment_variant"
        ),
        sa.CheckConstraint("variant IN ('A', 'B')", name="ck_tool_enrichment_variant"),
        sa.CheckConstraint(
            "(variant = 'A' AND extraction_used = false) OR "
            "(variant = 'B' AND extraction_used = true)",
            name="ck_tool_enrichment_extraction_variant",
        ),
    )
    op.create_index(
        "ix_tool_enrichments_experiment_variant",
        "tool_enrichments",
        ["experiment_id", "variant"],
    )
    op.create_index("ix_tool_enrichments_status", "tool_enrichments", ["status"])

    op.create_table(
        "tool_embeddings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tool_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("enrichment_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("embedding_type", sa.String(length=50), nullable=False),
        sa.Column("embedding_model", sa.String(length=200), nullable=False),
        sa.Column("actual_model", sa.String(length=200), nullable=True),
        sa.Column("embedding_batch_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("request_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("elapsed_seconds", sa.Float(), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("vector", Vector(768), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["tool_id"], ["tool_metadata.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["enrichment_id"], ["tool_enrichments.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tool_embeddings_tool_id", "tool_embeddings", ["tool_id"])
    op.create_index(
        "ix_tool_embeddings_enrichment_id", "tool_embeddings", ["enrichment_id"]
    )
    op.create_index(
        "ix_tool_embeddings_embedding_batch_id",
        "tool_embeddings",
        ["embedding_batch_id"],
    )
    op.create_index(
        "uq_tool_embedding_source",
        "tool_embeddings",
        ["tool_id", "embedding_type", "embedding_model"],
        unique=True,
        postgresql_where=sa.text("enrichment_id IS NULL"),
    )
    op.create_index(
        "uq_tool_enrichment_embedding",
        "tool_embeddings",
        ["enrichment_id", "embedding_type", "embedding_model"],
        unique=True,
        postgresql_where=sa.text("enrichment_id IS NOT NULL"),
    )
    op.create_index(
        "ix_tool_embeddings_enriched_description_hnsw",
        "tool_embeddings",
        ["vector"],
        postgresql_using="hnsw",
        postgresql_ops={"vector": "vector_cosine_ops"},
        postgresql_with={"m": 16, "ef_construction": 64},
        postgresql_where=sa.text(
            "embedding_type = 'enriched_description' "
            "AND embedding_model = 'nomic-embed-text-v2-moe'"
        ),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_tool_embeddings_enriched_description_hnsw", table_name="tool_embeddings"
    )
    op.drop_index("uq_tool_enrichment_embedding", table_name="tool_embeddings")
    op.drop_index("uq_tool_embedding_source", table_name="tool_embeddings")
    op.drop_index("ix_tool_embeddings_embedding_batch_id", table_name="tool_embeddings")
    op.drop_index("ix_tool_embeddings_enrichment_id", table_name="tool_embeddings")
    op.drop_index("ix_tool_embeddings_tool_id", table_name="tool_embeddings")
    op.drop_table("tool_embeddings")
    op.drop_index("ix_tool_enrichments_status", table_name="tool_enrichments")
    op.drop_index(
        "ix_tool_enrichments_experiment_variant", table_name="tool_enrichments"
    )
    op.drop_table("tool_enrichments")
    op.execute("DROP TRIGGER IF EXISTS trg_tool_search_types ON tool_metadata")
    op.execute("DROP FUNCTION IF EXISTS update_tool_search_types()")
    op.drop_index("ix_tool_metadata_search_types_gin", table_name="tool_metadata")
    op.drop_column("tool_metadata", "search_types")
