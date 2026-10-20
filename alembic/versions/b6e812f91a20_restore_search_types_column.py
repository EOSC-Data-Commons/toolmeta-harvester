"""Restore the derived search_types column expected by ToolMetadata.

Revision ID: b6e812f91a20
Revises: a13c45ee79d1
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b6e812f91a20"
down_revision: str | Sequence[str] | None = "a13c45ee79d1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tool_metadata",
        sa.Column(
            "search_types",
            postgresql.ARRAY(sa.Text()),
            server_default="{}",
            nullable=False,
            comment=(
                "Derived field: normalised, deduplicated type labels extracted from "
                "types, programming_languages, runtime_platforms and software_types."
            ),
        ),
    )
    op.create_index(
        "ix_tool_metadata_search_types_gin",
        "tool_metadata",
        ["search_types"],
        postgresql_using="gin",
    )
    op.execute(
        """CREATE OR REPLACE FUNCTION update_tool_search_types()
        RETURNS trigger AS $$
        BEGIN
            SELECT ARRAY(
                SELECT DISTINCT lower(trim(value))
                FROM (
                    SELECT unnest(coalesce(NEW.types, ARRAY[]::text[])) AS value
                    UNION ALL
                    SELECT obj->>'name'
                    FROM jsonb_array_elements(coalesce(NEW.programming_languages, '[]'::jsonb)) AS obj
                    UNION ALL
                    SELECT obj->>'name'
                    FROM jsonb_array_elements(coalesce(NEW.runtime_platforms, '[]'::jsonb)) AS obj
                    UNION ALL
                    SELECT obj->>'name'
                    FROM jsonb_array_elements(coalesce(NEW.software_types, '[]'::jsonb)) AS obj
                ) AS values
                WHERE value IS NOT NULL AND trim(value) <> ''
            ) INTO NEW.search_types;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql"""
    )
    op.execute("DROP TRIGGER IF EXISTS trg_tool_search_types ON tool_metadata")
    op.execute(
        """CREATE TRIGGER trg_tool_search_types
        BEFORE INSERT OR UPDATE OF types, programming_languages,
            runtime_platforms, software_types
        ON tool_metadata FOR EACH ROW
        EXECUTE FUNCTION update_tool_search_types()"""
    )
    op.execute("UPDATE tool_metadata SET types = types")


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_tool_search_types ON tool_metadata")
    op.execute("DROP FUNCTION IF EXISTS update_tool_search_types()")
    op.drop_index("ix_tool_metadata_search_types_gin", table_name="tool_metadata")
    op.drop_column("tool_metadata", "search_types")
