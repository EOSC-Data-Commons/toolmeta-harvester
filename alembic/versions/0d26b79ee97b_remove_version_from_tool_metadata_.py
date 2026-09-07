"""remove version from tool metadata unique constraint

Revision ID: 0d26b79ee97b
Revises: ac123157b86e
Create Date: 2026-08-26 09:20:33.776836

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0d26b79ee97b"
down_revision: Union[str, Sequence[str], None] = "ac123157b86e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint(
        "uq_tool_metadata_source_url_identifier_version",
        "tool_metadata",
        type_="unique",
    )

    op.create_unique_constraint(
        "uq_tool_metadata_source",
        "tool_metadata",
        [
            "source_url",
            "source_identifier",
        ],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_tool_metadata_source",
        "tool_metadata",
        type_="unique",
    )

    op.create_unique_constraint(
        "uq_tool_metadata_source_url_identifier_version",
        "tool_metadata",
        [
            "source_url",
            "source_identifier",
            "version",
        ],
    )
