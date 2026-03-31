"""add input/ouput description columns

Revision ID: a3ea695e40aa
Revises: 
Create Date: 2026-03-23 15:10:32.926167

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a3ea695e40aa'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "tool_generic",
        sa.Column(
            "input_file_descriptions",
            sa.ARRAY(sa.Text()),
            nullable=True,
        ),
    )

    op.add_column(
        "tool_generic",
        sa.Column(
            "output_file_descriptions",
            sa.ARRAY(sa.Text()),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("tool_generic", "output_file_descriptions")
    op.drop_column("tool_generic", "input_file_descriptions")
