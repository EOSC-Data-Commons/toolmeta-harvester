"""Move enrichment results into experiment-aware tables.

Revision ID: a13c45ee79d1
Revises: 9be70ae85cc1
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a13c45ee79d1"
down_revision: str | Sequence[str] | None = "9be70ae85cc1"
branch_labels = None
depends_on = None

LEGACY_RUN_ID = "a13c45ee-79d1-4e10-a13c-45ee79d14e10"


def upgrade() -> None:
    op.create_table(
        "tool_enrichment_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column(
            "status",
            sa.String(length=30),
            server_default="running",
            nullable=False,
        ),
        sa.Column("requested_extraction_model", sa.String(length=200), nullable=False),
        sa.Column("requested_generation_model", sa.String(length=200), nullable=False),
        sa.Column("requested_validation_model", sa.String(length=200), nullable=False),
        sa.Column("extraction_prompt_version", sa.String(length=100), nullable=False),
        sa.Column("generation_prompt_version", sa.String(length=100), nullable=False),
        sa.Column("validation_prompt_version", sa.String(length=100), nullable=False),
        sa.Column("sample_size", sa.Integer(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "tool_enrichments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tool_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "status", sa.String(length=20), server_default="pending", nullable=False
        ),
        sa.Column("input_hash", sa.String(length=64), nullable=True),
        sa.Column("input_description", sa.Text(), nullable=True),
        sa.Column("output_description", sa.Text(), nullable=True),
        sa.Column(
            "semantic_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
        sa.Column("enriched_description", sa.Text(), nullable=True),
        sa.Column("validation", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("extraction_model", sa.String(length=200), nullable=True),
        sa.Column("generation_model", sa.String(length=200), nullable=True),
        sa.Column("validation_model", sa.String(length=200), nullable=True),
        sa.Column("extraction_prompt_version", sa.String(length=100), nullable=True),
        sa.Column("generation_prompt_version", sa.String(length=100), nullable=True),
        sa.Column("validation_prompt_version", sa.String(length=100), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("failed_stage", sa.String(length=20), nullable=True),
        sa.Column("enriched_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["tool_id"], ["tool_metadata.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["run_id"], ["tool_enrichment_runs.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tool_id", "run_id", name="uq_tool_enrichment_run"),
    )
    op.create_index(
        "ix_tool_enrichments_run_status", "tool_enrichments", ["run_id", "status"]
    )

    # Existing run configuration was recorded in the experiment logs. The actual
    # response model was not persisted, so legacy actual-model columns stay NULL.
    op.execute(
        sa.text(
            """INSERT INTO tool_enrichment_runs (
                id, name, status, requested_extraction_model,
                requested_generation_model, requested_validation_model,
                extraction_prompt_version, generation_prompt_version,
                validation_prompt_version, sample_size, notes, finished_at
            ) SELECT CAST(:run_id AS uuid), 'legacy-qwen3.8-27b', 'completed',
                'qwen3.8-27b', 'qwen3.8-27b', 'qwen3.8-27b',
                'extraction_v1', 'generation_v1', 'validation_v1',
                count(*)::integer,
                'Migrated legacy results. Requested model is known; actual response model was not stored.',
                now()
              FROM tool_metadata WHERE enrichment_input_hash IS NOT NULL"""
        ).bindparams(run_id=LEGACY_RUN_ID)
    )
    op.execute(
        sa.text(
            """INSERT INTO tool_enrichments (
                id, tool_id, run_id, status, input_hash, input_description,
                output_description, semantic_metadata, enriched_description,
                validation, extraction_prompt_version, generation_prompt_version,
                validation_prompt_version, error, failed_stage, enriched_at
            ) SELECT gen_random_uuid(), id, CAST(:run_id AS uuid), enrichment_status,
                enrichment_input_hash, input_description, output_description,
                semantic_metadata, enriched_description, enrichment_validation,
                split_part(coalesce(enrichment_version, ''), '+', 1),
                nullif(split_part(coalesce(enrichment_version, ''), '+', 2), ''),
                nullif(split_part(coalesce(enrichment_version, ''), '+', 3), ''),
                enrichment_error, enrichment_failed_stage, enriched_at
              FROM tool_metadata WHERE enrichment_input_hash IS NOT NULL"""
        ).bindparams(run_id=LEGACY_RUN_ID)
    )

    op.add_column(
        "tool_embeddings",
        sa.Column("enrichment_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_tool_embeddings_enrichment_id",
        "tool_embeddings",
        "tool_enrichments",
        ["enrichment_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        "ix_tool_embeddings_enrichment_id", "tool_embeddings", ["enrichment_id"]
    )
    op.drop_constraint("uq_tool_embedding", "tool_embeddings", type_="unique")
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

    op.drop_index("ix_tool_metadata_enrichment_status", table_name="tool_metadata")
    for column in (
        "enriched_at",
        "enrichment_validation",
        "enrichment_failed_stage",
        "enrichment_error",
        "enrichment_version",
        "enrichment_input_hash",
        "enrichment_status",
        "enriched_description",
        "semantic_metadata",
        "output_description",
        "input_description",
    ):
        op.drop_column("tool_metadata", column)


def downgrade() -> None:
    for name in (
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
    ):
        column_type = {
            "semantic_metadata": postgresql.JSONB(astext_type=sa.Text()),
            "enrichment_validation": postgresql.JSONB(astext_type=sa.Text()),
            "enriched_at": sa.DateTime(timezone=True),
            "enrichment_status": sa.String(length=20),
            "enrichment_input_hash": sa.String(length=64),
            "enrichment_version": sa.String(length=100),
            "enrichment_failed_stage": sa.String(length=20),
            "input_description": sa.Text(),
            "output_description": sa.Text(),
            "enriched_description": sa.Text(),
            "enrichment_error": sa.Text(),
        }[name]
        op.add_column("tool_metadata", sa.Column(name, column_type, nullable=True))
    op.execute(
        """UPDATE tool_metadata tm SET
            input_description = te.input_description,
            output_description = te.output_description,
            semantic_metadata = te.semantic_metadata,
            enriched_description = te.enriched_description,
            enrichment_status = te.status,
            enrichment_input_hash = te.input_hash,
            enrichment_version = concat_ws('+', te.extraction_prompt_version,
                te.generation_prompt_version, te.validation_prompt_version),
            enrichment_error = te.error,
            enrichment_failed_stage = te.failed_stage,
            enrichment_validation = te.validation,
            enriched_at = te.enriched_at
          FROM tool_enrichments te
          WHERE te.tool_id = tm.id AND te.run_id = (
              SELECT id FROM tool_enrichment_runs ORDER BY started_at DESC LIMIT 1
          )"""
    )
    op.alter_column(
        "tool_metadata", "enrichment_status", nullable=False, server_default="pending"
    )
    op.create_index(
        "ix_tool_metadata_enrichment_status", "tool_metadata", ["enrichment_status"]
    )

    op.drop_index(
        "ix_tool_embeddings_enriched_description_hnsw", table_name="tool_embeddings"
    )
    op.drop_index("uq_tool_enrichment_embedding", table_name="tool_embeddings")
    op.drop_index("uq_tool_embedding_source", table_name="tool_embeddings")
    op.create_unique_constraint(
        "uq_tool_embedding",
        "tool_embeddings",
        ["tool_id", "embedding_type", "embedding_model"],
    )
    op.drop_index("ix_tool_embeddings_enrichment_id", table_name="tool_embeddings")
    op.drop_constraint(
        "fk_tool_embeddings_enrichment_id", "tool_embeddings", type_="foreignkey"
    )
    op.drop_column("tool_embeddings", "enrichment_id")
    op.drop_index("ix_tool_enrichments_run_status", table_name="tool_enrichments")
    op.drop_table("tool_enrichments")
    op.drop_table("tool_enrichment_runs")
