import logging

# from importlib.metadata import version
from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.schema import CreateColumn

from toolmeta_harvester.db.engine import Base, engine
from toolmeta_harvester.db.models import (
    ToolMetadata,
    ToolEmbedding,
    HarvestSource,
)
from toolmeta_harvester.db.triggers import (
    ensure_tool_search_types_trigger,
    populate_tool_search_types,
)


logger = logging.getLogger(__name__)

# LIBRARY_VERSION = version("toolmeta-harvester")
SCHEMA_VERSION = 1
TABLES = [
    ToolMetadata.__table__,
    ToolEmbedding.__table__,
    HarvestSource.__table__,
]
INIT_LOCK_ID = 7355608


def ensure_columns(conn: Connection) -> None:
    """Add missing columns defined in the SQLAlchemy models."""

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
                    f"{table.name}.{column.name} without a server default"
                )

            column_ddl = str(CreateColumn(column).compile(dialect=conn.dialect))

            sql = f"ALTER TABLE {table_name} ADD COLUMN IF NOT EXISTS {column_ddl}"

            logger.info(
                "Adding column %s.%s",
                table.name,
                column.name,
            )

            conn.execute(text(sql))


def ensure_indexes(conn: Connection) -> None:
    """Create missing indexes."""

    inspector = inspect(conn)

    for table in TABLES:
        existing = {
            index["name"]
            for index in inspector.get_indexes(
                table.name,
                schema=table.schema,
            )
        }

        for index in table.indexes:
            if index.name in existing:
                continue

            logger.info(
                "Creating index: %s on %s",
                index.name,
                table.name,
            )

            index.create(bind=conn, checkfirst=True)


def initialize_db(populate_search_types: bool = False) -> None:
    with engine.begin() as conn:
        conn.execute(text("SELECT pg_advisory_xact_lock(7355608)"))

        conn.execute(
            text("""
            CREATE TABLE IF NOT EXISTS toolmeta_schema_version (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                version INTEGER NOT NULL
            )
        """)
        )

        installed_version = conn.scalar(
            text("""
            SELECT version
            FROM toolmeta_schema_version
            WHERE id = 1
        """)
        )

        if installed_version is not None:
            if installed_version > SCHEMA_VERSION:
                raise RuntimeError(
                    f"Database schema version {installed_version} "
                    f"is newer than supported version {SCHEMA_VERSION}"
                )

            if installed_version == SCHEMA_VERSION:
                logger.debug("Database schema is up to date")
                return

        logger.info(
            "Updating database schema: %s -> %s",
            installed_version,
            SCHEMA_VERSION,
        )

        Base.metadata.create_all(
            bind=conn,
            tables=TABLES,
            checkfirst=True,
        )

        ensure_columns(conn)
        ensure_indexes(conn)
        ensure_tool_search_types_trigger(conn)

        if populate_search_types:
            populate_tool_search_types(conn)

        conn.execute(
            text("""
                INSERT INTO toolmeta_schema_version (id, version)
                VALUES (1, :version)
                ON CONFLICT (id)
                DO UPDATE SET version = EXCLUDED.version
            """),
            {"version": SCHEMA_VERSION},
        )


# import logging
# from sqlalchemy.engine import Engine
# from sqlalchemy.schema import CreateColumn
#
# from sqlalchemy import inspect, text
# from contextlib import contextmanager
#
# from toolmeta_harvester.db.engine import Base, engine
# from toolmeta_harvester.db.models import ToolMetadata, ToolEmbedding
# from toolmeta_harvester.db.triggers import (
#     ensure_tool_search_types_trigger,
#     populate_tool_search_types,
# )
#
#
# logger = logging.getLogger(__name__)
#
# TABLES = [
#     ToolMetadata.__table__,
#     ToolEmbedding.__table__,
# ]
#
#
# def ensure_indexes(engine: Engine) -> None:
#     """Create missing indexes for ToolMetadata and ToolEmbedding."""
#
#     with engine.begin() as conn:
#         for table in TABLES:
#             existing = {
#                 index["name"] for index in inspect(conn).get_indexes(table.name)
#             }
#
#             for index in table.indexes:
#                 if index.name in existing:
#                     logger.debug(
#                         "Index already exists: %s",
#                         index.name,
#                     )
#                     continue
#
#                 logger.info(
#                     "Creating index: %s on %s",
#                     index.name,
#                     table.name,
#                 )
#
#                 index.create(bind=conn, checkfirst=True)
#
#                 logger.info("Created index: %s", index.name)
#
#
# def ensure_columns(engine: Engine) -> None:
#     """Add missing columns defined in the SQLAlchemy models."""
#
#     with engine.begin() as conn:
#         inspector = inspect(conn)
#         preparer = conn.dialect.identifier_preparer
#
#         for table in TABLES:
#             existing = {
#                 col["name"]
#                 for col in inspector.get_columns(
#                     table.name,
#                     schema=table.schema,
#                 )
#             }
#
#             table_name = preparer.format_table(table)
#
#             for column in table.columns:
#                 if column.name in existing:
#                     continue
#
#                 if column.primary_key or column.foreign_keys:
#                     raise RuntimeError(
#                         f"Column {table.name}.{column.name} requires "
#                         "an explicit database migration"
#                     )
#
#                 if (
#                     not column.nullable
#                     and column.server_default is None
#                     and column.computed is None
#                 ):
#                     raise RuntimeError(
#                         f"Cannot automatically add NOT NULL column "
#                         f"{table.name}.{column.name} without a "
#                         "server default"
#                     )
#
#                 column_ddl = str(CreateColumn(column).compile(dialect=conn.dialect))
#
#                 sql = f"ALTER TABLE {table_name} ADD COLUMN IF NOT EXISTS {column_ddl}"
#
#                 logger.info(
#                     "Adding column %s.%s",
#                     table.name,
#                     column.name,
#                 )
#
#                 conn.execute(text(sql))
#
#
# @contextmanager
# def database_init_lock(engine):
#     lock_id = 7355608
#
#     with engine.connect() as conn:
#         conn.execute(
#             text("SELECT pg_advisory_lock(:lock_id)"),
#             {"lock_id": lock_id},
#         )
#         conn.commit()
#
#         try:
#             yield
#         finally:
#             conn.execute(
#                 text("SELECT pg_advisory_unlock(:lock_id)"),
#                 {"lock_id": lock_id},
#             )
#             conn.commit()
#
#
# def initialize_db(populate_search_types=False) -> None:
#     """Initialise tables, triggers, derived fields and indexes."""
#
#     with database_init_lock(engine):
#         Base.metadata.create_all(bind=engine)
#
#         ensure_columns(engine)
#
#         ensure_tool_search_types_trigger(engine)
#
#         if populate_search_types:
#             updated = populate_tool_search_types(engine)
#             logger.info("Populated search_types for %d tools", updated)
#
#         ensure_indexes(engine)
