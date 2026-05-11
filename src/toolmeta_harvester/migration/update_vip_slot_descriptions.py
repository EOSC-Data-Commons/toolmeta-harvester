import logging
import copy
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy import any_
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

        stmt = (
                select(ToolGeneric)
                .where("vip" == any_(ToolGeneric.types))
        )

        for tool in session.scalars(stmt):

            # print("------------")
            # print(f"id          : {tool.id}")
            # print(f"uri         : {tool.uri}")
            # print(f"name        : {tool.name}")
            # print(f"description : {tool.description}")
            # print(f"inputs      : {tool.input_slots}")

            # Make a copy so SQLAlchemy sees reassignment
            input_slots = copy.deepcopy(tool.input_slots)           

            raw_defintion = tool.raw_definition

            for inputs in raw_defintion.get("inputs", []):
                input_id = inputs.get("id")

                for slot in input_slots:
                    if "optional" not in slot:
                        if slot["id"] == input_id:
                            print(f"Updating input slot: '{slot["id"]}' for tool '{tool.id}'")
                            slot["optional"] = inputs.get("optional", False)
                            slot["default"] = inputs.get("default-value", None)

            # Assign the modified input_slots back to the tool
            tool.input_slots = input_slots

            session.commit()
                        



if __name__ == "__main__":
    main()
