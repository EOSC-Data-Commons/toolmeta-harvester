"""Represent the legacy schema revision that predates repository history."""

from collections.abc import Sequence

revision: str = "0d26b79ee97b"
down_revision: str | Sequence[str] | None = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The source schema is initialized by the harvester's existing database setup.
    # This no-op revision preserves the deployed revision identifier.
    pass


def downgrade() -> None:
    pass
