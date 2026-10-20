"""Create the table described by the existing ToolEmbedding model.

The audited local database had neither the vector extension nor the table.
The model and embedding task already expect 768-dimensional pgvector storage.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "9be70ae85cc1"
down_revision: str | Sequence[str] | None = "8c25d72b21a4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "tool_embeddings",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tool_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("embedding_type", sa.String(length=50), nullable=False),
        sa.Column("embedding_model", sa.String(length=200), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("vector", Vector(768), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["tool_id"], ["tool_metadata.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tool_id", "embedding_type", "embedding_model", name="uq_tool_embedding"
        ),
    )
    op.create_index("ix_tool_embeddings_tool_id", "tool_embeddings", ["tool_id"])


def downgrade() -> None:
    op.drop_index("ix_tool_embeddings_tool_id", table_name="tool_embeddings")
    op.drop_table("tool_embeddings")
