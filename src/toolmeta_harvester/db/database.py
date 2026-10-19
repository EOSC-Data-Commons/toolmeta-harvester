import logging
from sqlalchemy.engine import Engine
from sqlalchemy.schema import CreateColumn

from sqlalchemy import inspect, text
from toolmeta_harvester.db.engine import Base, engine
from toolmeta_harvester.db.models import ToolMetadata, ToolEmbedding
from toolmeta_harvester.db.triggers import (
    ensure_tool_search_types_trigger,
    populate_tool_search_types,
)


logger = logging.getLogger(__name__)

TABLES = [
    ToolMetadata.__table__,
    ToolEmbedding.__table__,
]


def ensure_indexes(engine: Engine) -> None:
    """Create missing indexes for ToolMetadata and ToolEmbedding."""

    with engine.begin() as conn:
        for table in TABLES:
            existing = {
                index["name"] for index in inspect(conn).get_indexes(table.name)
            }

            for index in table.indexes:
                if index.name in existing:
                    logger.debug(
                        "Index already exists: %s",
                        index.name,
                    )
                    continue

                logger.info(
                    "Creating index: %s on %s",
                    index.name,
                    table.name,
                )

                index.create(bind=conn, checkfirst=True)

                logger.info("Created index: %s", index.name)


def ensure_columns(engine: Engine) -> None:
    """Add missing columns defined in the SQLAlchemy models."""

    with engine.begin() as conn:
        inspector = inspect(conn)
        preparer = conn.dialect.identifier_preparer

        for table in TABLES:
            existing = {
                col["name"]
                for col in inspector.get_columns(
                    table.name,
                    schema=table.schema,
                )
            }

            table_name = preparer.format_table(table)

            for column in table.columns:
                if column.name in existing:
                    continue

                if column.primary_key or column.foreign_keys:
                    raise RuntimeError(
                        f"Column {table.name}.{column.name} requires "
                        "an explicit database migration"
                    )

                if (
                    not column.nullable
                    and column.server_default is None
                    and column.computed is None
                ):
                    raise RuntimeError(
                        f"Cannot automatically add NOT NULL column "
                        f"{table.name}.{column.name} without a "
                        "server default"
                    )

                column_ddl = str(CreateColumn(column).compile(dialect=conn.dialect))

                sql = f"ALTER TABLE {table_name} ADD COLUMN IF NOT EXISTS {column_ddl}"

                logger.info(
                    "Adding column %s.%s",
                    table.name,
                    column.name,
                )

                conn.execute(text(sql))


def initialize_db(populate_search_types=False) -> None:
    """Initialise tables, triggers, derived fields and indexes."""

    Base.metadata.create_all(bind=engine)

    ensure_columns(engine)

    ensure_tool_search_types_trigger(engine)

    if populate_search_types:
        updated = populate_tool_search_types(engine)
        logger.info("Populated search_types for %d tools", updated)

    ensure_indexes(engine)
