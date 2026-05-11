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

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(name)s %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> None:
    """Create all tables in the database."""
    Base.metadata.create_all(engine)

    with Session(engine) as session:

        stmt = select(ToolGeneric)

        for tool in session.scalars(stmt):

            print("------------")
            print(f"id          : {tool.id}")
            print(f"uri         : {tool.uri}")
            print(f"name        : {tool.name}")
            print(f"description : {tool.description}")

            # TODO: Enrich logic here.


if __name__ == "__main__":
    main()
