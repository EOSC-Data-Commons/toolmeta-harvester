from sqlalchemy import text, DDL, event
from sqlalchemy.engine import Engine
from toolmeta_harvester.db.models import ToolMetadata

CREATE_SEARCH_TYPES_FUNCTION = DDL("""
CREATE OR REPLACE FUNCTION update_tool_search_types()
RETURNS trigger AS $$
BEGIN
    SELECT ARRAY(
        SELECT DISTINCT lower(trim(value))
        FROM (
            SELECT unnest(NEW.types) AS value

            UNION ALL

            SELECT obj->>'name'
            FROM jsonb_array_elements(
                NEW.programming_languages
            ) AS obj

            UNION ALL

            SELECT obj->>'name'
            FROM jsonb_array_elements(
                NEW.runtime_platforms
            ) AS obj

            UNION ALL

            SELECT obj->>'name'
            FROM jsonb_array_elements(
                NEW.software_types
            ) AS obj
        ) AS values
        WHERE value IS NOT NULL
          AND trim(value) <> ''
    )
    INTO NEW.search_types;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
""")


CREATE_SEARCH_TYPES_TRIGGER = DDL("""
CREATE OR REPLACE TRIGGER trg_tool_search_types
BEFORE INSERT OR UPDATE OF
    types,
    programming_languages,
    runtime_platforms,
    software_types
ON tool_metadata
FOR EACH ROW
EXECUTE FUNCTION update_tool_search_types();
""")

# Register listeners when this module is imported.
event.listen(
    ToolMetadata.__table__,
    "after_create",
    CREATE_SEARCH_TYPES_FUNCTION.execute_if(dialect="postgresql"),
)

event.listen(
    ToolMetadata.__table__,
    "after_create",
    CREATE_SEARCH_TYPES_TRIGGER.execute_if(dialect="postgresql"),
)


def ensure_tool_search_types_trigger(engine: Engine) -> None:
    """Create or replace the trigger maintaining search_types."""

    with engine.begin() as conn:
        conn.execute(CREATE_SEARCH_TYPES_FUNCTION)
        conn.execute(CREATE_SEARCH_TYPES_TRIGGER)


def populate_tool_search_types(engine: Engine) -> int:
    """Populate missing or empty search_types using the database trigger."""

    with engine.begin() as conn:
        result = conn.execute(
            text("""
                UPDATE tool_metadata
                SET types = types
                WHERE search_types IS NULL
                   OR search_types = '{}';
            """)
        )

        return result.rowcount
