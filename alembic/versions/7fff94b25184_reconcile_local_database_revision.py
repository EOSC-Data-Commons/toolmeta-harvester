"""Record the locally deployed schema baseline before enrichment changes.

The development ``tooldb`` database was at revision 7fff94b25184, which was
not present in this checkout. Inspection confirmed the tool_metadata columns
and constraints expected after the checked-in 0d26b79ee97b migration. This
no-op bridge lets Alembic continue from that existing database state.
"""

from collections.abc import Sequence

revision: str = "7fff94b25184"
down_revision: str | Sequence[str] | None = "0d26b79ee97b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
