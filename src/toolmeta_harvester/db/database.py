"""Initialize ordinary harvester tables; Alembic owns enrichment schema changes."""

import logging
from typing import cast

from sqlalchemy import Table, inspect, text
from sqlalchemy.engine import Connection
from sqlalchemy.schema import CreateColumn

from toolmeta_harvester.db.engine import Base, engine
from toolmeta_harvester.db.models import HarvestSource, ToolMetadata
from toolmeta_harvester.db.triggers import (
    ensure_tool_search_types_trigger,
    populate_tool_search_types,
)

logger = logging.getLogger(__name__)
HARVEST_TABLES = cast(
    tuple[Table, ...], (ToolMetadata.__table__, HarvestSource.__table__)
)
INIT_LOCK_ID = 7355608


def _ensure_columns(conn: Connection) -> None:
    inspector = inspect(conn)
    preparer = conn.dialect.identifier_preparer
    for table in HARVEST_TABLES:
        existing = {
            col["name"]
            for col in inspector.get_columns(table.name, schema=table.schema)
        }
        table_name = preparer.format_table(table)
        for column in table.columns:
            if column.name in existing:
                continue
            if column.primary_key or column.foreign_keys:
                raise RuntimeError(
                    f"Column {table.name}.{column.name} requires an Alembic migration"
                )
            if (
                not column.nullable
                and column.server_default is None
                and column.computed is None
            ):
                raise RuntimeError(
                    f"Cannot add NOT NULL column {table.name}.{column.name} without a default"
                )
            conn.execute(
                text(
                    f"ALTER TABLE {table_name} ADD COLUMN IF NOT EXISTS {CreateColumn(column).compile(dialect=conn.dialect)}"
                )
            )


def _ensure_indexes(conn: Connection) -> None:
    inspector = inspect(conn)
    for table in HARVEST_TABLES:
        existing = {
            idx["name"]
            for idx in inspector.get_indexes(table.name, schema=table.schema)
        }
        for index in table.indexes:
            if index.name not in existing:
                index.create(bind=conn, checkfirst=True)


def initialize_db(populate_search_types: bool = False) -> None:
    """Create/update only harvesting tables, never enrichment tables."""
    with engine.begin() as conn:
        conn.execute(
            text("SELECT pg_advisory_xact_lock(:lock_id)"), {"lock_id": INIT_LOCK_ID}
        )
        Base.metadata.create_all(bind=conn, tables=HARVEST_TABLES, checkfirst=True)
        _ensure_columns(conn)
        _ensure_indexes(conn)
        ensure_tool_search_types_trigger(conn)
        if populate_search_types:
            populate_tool_search_types(conn)
        logger.info(
            "Harvester source tables are ready; enrichment schema is managed by Alembic"
        )
