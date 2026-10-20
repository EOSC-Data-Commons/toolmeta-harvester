"""Add fields used by the experimental semantic enrichment pipeline.

Revision ID: 8c25d72b21a4
Revises: 7fff94b25184
Create Date: 2026-10-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "8c25d72b21a4"
down_revision: str | Sequence[str] | None = "7fff94b25184"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tool_metadata", sa.Column("input_description", sa.Text(), nullable=True)
    )
    op.add_column(
        "tool_metadata", sa.Column("output_description", sa.Text(), nullable=True)
    )
    op.add_column(
        "tool_metadata",
        sa.Column(
            "semantic_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
    )
    op.add_column(
        "tool_metadata", sa.Column("enriched_description", sa.Text(), nullable=True)
    )
    op.add_column(
        "tool_metadata",
        sa.Column(
            "enrichment_status",
            sa.String(length=20),
            server_default="pending",
            nullable=False,
        ),
    )
    op.add_column(
        "tool_metadata",
        sa.Column("enrichment_input_hash", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "tool_metadata",
        sa.Column("enrichment_version", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "tool_metadata", sa.Column("enrichment_error", sa.Text(), nullable=True)
    )
    op.add_column(
        "tool_metadata",
        sa.Column("enrichment_failed_stage", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "tool_metadata",
        sa.Column(
            "enrichment_validation",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )
    op.add_column(
        "tool_metadata",
        sa.Column("enriched_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_tool_metadata_enrichment_status",
        "tool_metadata",
        ["enrichment_status"],
    )


def downgrade() -> None:
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
