"""add gin indexes

Revision ID: 7fff94b25184
Revises: 1ae51acc54dc
Create Date: 2026-06-01 13:18:56.111354

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7fff94b25184'
down_revision: Union[str, Sequence[str], None] = '1ae51acc54dc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    op.create_index(
        "idx_tool_generic_input_file_formats",
        "tool_generic",
        ["input_file_formats"],
        postgresql_using="gin",
    )

    op.create_index(
        "idx_tool_generic_output_file_formats",
        "tool_generic",
        ["output_file_formats"],
        postgresql_using="gin",
    )

def downgrade():
    op.drop_index("idx_tool_generic_input_file_formats")
    op.drop_index("idx_tool_generic_output_file_formats")
