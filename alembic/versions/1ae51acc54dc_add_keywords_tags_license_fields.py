"""add keywords, tags, license fields

Revision ID: 1ae51acc54dc
Revises: a3ea695e40aa
Create Date: 2026-03-31 18:47:31.713659

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1ae51acc54dc'
down_revision: Union[str, Sequence[str], None] = 'a3ea695e40aa'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "tool_generic",
        sa.Column("keywords", sa.ARRAY(sa.Text()), nullable=True)
    )
    op.add_column(
        "tool_generic",
        sa.Column("tags", sa.ARRAY(sa.Text()), nullable=True)
    )
    op.add_column(
        "tool_generic",
        sa.Column("license", sa.String(length=255), nullable=True)
    )

    pass


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("tool_generic", "license")
    op.drop_column("tool_generic", "tags")
    op.drop_column("tool_generic", "keywords")
    pass
