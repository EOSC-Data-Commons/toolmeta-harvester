"""Record explicit AI-generation provenance on enrichment attempts."""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "f4bd681f91f2"
down_revision: str | Sequence[str] | None = "ea53f4a99f01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {
        column["name"]
        for column in sa.inspect(op.get_bind()).get_columns("tool_metadata_enrichment")
    }
    if "is_ai_generated" not in columns:
        op.add_column(
            "tool_metadata_enrichment",
            sa.Column(
                "is_ai_generated",
                sa.Boolean(),
                server_default=sa.false(),
                nullable=False,
            ),
        )
        op.execute(
            "UPDATE tool_metadata_enrichment SET is_ai_generated = (status = 'generated')"
        )
    constraints = {
        item.get("name")
        for item in sa.inspect(op.get_bind()).get_check_constraints(
            "tool_metadata_enrichment"
        )
    }
    if "ck_tool_metadata_enrichment_ai_flag" not in constraints:
        op.create_check_constraint(
            "ck_tool_metadata_enrichment_ai_flag",
            "tool_metadata_enrichment",
            "(status = 'generated' AND is_ai_generated) OR (status <> 'generated' AND NOT is_ai_generated)",
        )


def downgrade() -> None:
    # Keep provenance when rolling application code back.
    pass
