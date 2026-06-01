import logging
from sqlalchemy import select
from sqlalchemy.orm import Session
from toolmeta_harvester import config
from toolmeta_harvester.db.engine import engine
from toolmeta_harvester.db.models import (
    Base,
)
from toolmeta_models import (
    ToolGeneric,
)
from sqlalchemy import text
from sqlalchemy.orm import Session

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(name)s %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)

def backfill_input_file_formats(session: Session) -> None:
    session.execute(text("""
        UPDATE tool_generic
        SET input_file_formats = sub.formats
        FROM (
            SELECT
                id,
                COALESCE(
                    ARRAY(
                        SELECT DISTINCT jsonb_array_elements_text(slot -> 'file_formats')
                        FROM jsonb_array_elements(input_slots) AS slot
                        WHERE slot ? 'file_formats'
                    ),
                    ARRAY[]::text[]
                ) AS formats
            FROM tool_generic
            WHERE input_slots IS NOT NULL
             AND (
                input_file_formats IS NULL
                OR array_length(input_file_formats, 1) IS NULL
              )
        ) AS sub
        WHERE tool_generic.id = sub.id;
    """))
    session.commit()

def backfill_output_file_formats(session: Session) -> None:
    session.execute(text("""
        UPDATE tool_generic
        SET output_file_formats = sub.formats
        FROM (
            SELECT
                id,
                COALESCE(
                    ARRAY(
                        SELECT DISTINCT jsonb_array_elements_text(slot -> 'file_formats')
                        FROM jsonb_array_elements(output_slots) AS slot
                        WHERE slot ? 'file_formats'
                    ),
                    ARRAY[]::text[]
                ) AS formats
            FROM tool_generic
            WHERE output_slots IS NOT NULL
            AND (
                    output_file_formats IS NULL
                    OR cardinality(output_file_formats) = 0
                )
        ) AS sub
        WHERE tool_generic.id = sub.id
        AND (
                tool_generic.output_file_formats IS NULL
                OR cardinality(tool_generic.output_file_formats) = 0
            );
    """))

    session.commit()


def main() -> None:
    """Create all tables in the database."""
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        backfill_input_file_formats(session)
        backfill_output_file_formats(session)


        # stmt = select(ToolGeneric)
        #
        # for tool in session.scalars(stmt):
        #
        #     print("------------")
        #     print(f"id          : {tool.id}")
        #     print(f"uri         : {tool.uri}")
        #     print(f"name        : {tool.name}")
        #     print(f"description : {tool.description}")
        #
        #     # TODO: Enrich logic here.


if __name__ == "__main__":
    main()
