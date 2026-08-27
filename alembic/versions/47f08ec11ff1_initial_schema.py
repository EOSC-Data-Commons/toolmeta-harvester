"""initial schema

Revision ID: 47f08ec11ff1
Revises:
Create Date: 2026-08-24 16:03:47.407198

"""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "47f08ec11ff1"
down_revision = None
branch_labels = None
depends_on = None


DEFAULT_MIN_DESCRIPTION_LENGTH = 40


def has_value(value: Any) -> bool:
    if value is None:
        return False

    if isinstance(value, str):
        return bool(value.strip())

    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)

    return True


def description_is_meaningful(
    description: str | None,
    min_length: int = DEFAULT_MIN_DESCRIPTION_LENGTH,
) -> bool:
    if not description:
        return False

    return len(description.strip()) >= min_length


def calculate_quality_score(row) -> float:
    """
    Frozen version of the metadata quality assessment used when this
    migration was created.

    Score is normalized to the range 0..1.
    """

    checks = {
        # Identity / findability
        "title": has_value(row.title),
        "identifier": has_value(row.identifiers),
        "url": has_value(row.url),
        # Description
        "description": description_is_meaningful(row.description),
        "keywords": has_value(row.keywords),
        # Reusability
        "license": has_value(row.license),
        "authors": has_value(row.authors),
        "version": has_value(row.version),
        # Software discoverability
        "types": has_value(row.types),
        "programming_languages": has_value(row.programming_languages),
        "runtime_platforms": has_value(row.runtime_platforms),
        # Scientific extensions
        "software_types": has_value(row.software_types),
        "consumes_data": has_value(row.consumes_data),
        "produces_data": has_value(row.produces_data),
    }

    weights = {
        "title": 1.5,
        "identifier": 1.5,
        "url": 1.0,
        "description": 2.0,
        "keywords": 0.5,
        "license": 1.5,
        "authors": 1.0,
        "version": 0.5,
        "types": 0.5,
        "programming_languages": 0.5,
        "runtime_platforms": 0.25,
        "software_types": 0.25,
        "consumes_data": 0.25,
        "produces_data": 0.25,
    }

    total = sum(weights.values())

    earned = sum(weight for name, weight in weights.items() if checks[name])

    return round(earned / total, 3)


def upgrade() -> None:
    # First allow NULL while existing records are assessed.
    op.add_column(
        "tool_metadata",
        sa.Column(
            "quality_score",
            sa.Float(),
            nullable=True,
        ),
    )

    bind = op.get_bind()

    tool_metadata = sa.table(
        "tool_metadata",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("title", sa.Text()),
        sa.column("description", sa.Text()),
        sa.column("version", sa.Text()),
        sa.column("license", sa.Text()),
        sa.column(
            "identifiers",
            postgresql.ARRAY(sa.Text()),
        ),
        sa.column("url", sa.Text()),
        sa.column(
            "keywords",
            postgresql.ARRAY(sa.Text()),
        ),
        sa.column(
            "authors",
            postgresql.JSONB(),
        ),
        sa.column(
            "types",
            postgresql.ARRAY(sa.Text()),
        ),
        sa.column(
            "programming_languages",
            postgresql.JSONB(),
        ),
        sa.column(
            "runtime_platforms",
            postgresql.JSONB(),
        ),
        sa.column(
            "software_types",
            postgresql.JSONB(),
        ),
        sa.column(
            "consumes_data",
            postgresql.JSONB(),
        ),
        sa.column(
            "produces_data",
            postgresql.JSONB(),
        ),
        sa.column(
            "quality_score",
            sa.Float(),
        ),
    )

    rows = bind.execute(
        sa.select(
            tool_metadata.c.id,
            tool_metadata.c.title,
            tool_metadata.c.description,
            tool_metadata.c.version,
            tool_metadata.c.license,
            tool_metadata.c.identifiers,
            tool_metadata.c.url,
            tool_metadata.c.keywords,
            tool_metadata.c.authors,
            tool_metadata.c.types,
            tool_metadata.c.programming_languages,
            tool_metadata.c.runtime_platforms,
            tool_metadata.c.software_types,
            tool_metadata.c.consumes_data,
            tool_metadata.c.produces_data,
        )
    )

    for row in rows:
        score = calculate_quality_score(row)

        bind.execute(
            sa.update(tool_metadata)
            .where(tool_metadata.c.id == row.id)
            .values(quality_score=score)
        )

    # Every existing row should now have a score.
    op.alter_column(
        "tool_metadata",
        "quality_score",
        existing_type=sa.Float(),
        nullable=False,
    )


def downgrade() -> None:
    op.drop_column(
        "tool_metadata",
        "quality_score",
    )
