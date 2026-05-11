
import logging
import copy
import json
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
                .where("galaxy_workflow" == any_(ToolGeneric.types))
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

            for k in raw_defintion.get("steps", []):
                step = raw_defintion["steps"][k]
                input_id = step.get("id", None)
                type = step.get("type", None)
                if type != "data_input":
                    continue
                if input_id is None:
                    continue
                input_id = int(input_id)
                label = step.get("label", None)


                for slot in input_slots:
                    if "optional" not in slot:
                        if int(slot["id"]) == input_id:
                            print(f"Updating input slot: '{slot["id"]}' for tool '{tool.id}'")
                            tool_state = json.loads(step["tool_state"])
                            slot["optional"] = tool_state.get("optional", False)
                            slot["default"] = None
                                

            # Assign the modified input_slots back to the tool
            tool.input_slots = input_slots

            session.commit()
                        



if __name__ == "__main__":
    main()
