import logging
from toolmeta_harvester.tasks import galaxy_toolshed as shed
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
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s: %(message)s",
)

logger = logging.getLogger(__name__)

def pipeline_harvest_single_toolshed_from_git(git_url, tool_name):

    results = []

    for url, tools in shed.smart_crawl_repository_iter(git_url, tool_name.lower()):
        for tool in tools:
            results.append(tool)

    return results


if __name__ == "__main__":
    # URL =      "https://github.com/BgeeDB/tools-iuc"
    REPO = "https://github.com/BgeeDB/tools-iuc/tree/main/tools/"
    TOOL = "topanat"
    URL = f"{REPO}{TOOL}"
    session = Session(engine)
    repo_api_url = shed.convert_git_url_to_api(REPO)
    logger.info(f"Converted Git URL to API URL: {repo_api_url}")
 
    tools = pipeline_harvest_single_toolshed_from_git(repo_api_url, TOOL)
    for tool in tools:
        logger.info(f"Tool ID: {tool.id}")
        logger.info(f"Tool Name: {tool.tool_name}")
        logger.info(f"Tool Version: {tool.version}")
        logger.info(f"Tool URI: {tool.uri}")
        logger.info(f"Tool Description: {tool.description}")
        # logger.info(f"Tool help: {tool.help}")
        # logger.info(f"Tool inputs: {tool.inputs}")

        inputs = []
        for input in tool.inputs:
            label_id = input.get("label", None)
            if label_id:
                label_id = label_id.replace(" ", "_").lower()
            input_dict = {
                "id": input.get("name") or label_id or None,
                "name": input.get("label", input["name"]),
                "description": input.get("description", None),
                "type": input.get("type", None),
                "optional": input.get("optional", False),
                "default": input.get("default", None),
                "file_formats": [
                    fmt.strip()
                    for fmt in (input.get("format") or "").split(",")
                    if fmt.strip()
                ],
            }
            inputs.append(input_dict)

        outputs = []
        for output in tool.outputs:
            label_id = output.get("label", None)
            if label_id:
                label_id = label_id.replace(" ", "_").lower()
            output_dict = {
                "id": output.get("name") or label_id or None,
                "name": output.get("label", output["name"]),
                "description": output.get("description", None),
                "type": output.get("type", None),
                "file_formats": [
                    fmt.strip()
                    for fmt in (output.get("format") or "").split(",")
                    if fmt.strip()
                ],
            }
            outputs.append(output_dict)

        shed_generic = ToolGeneric(
            uri = URL,
            location = URL,
            name = tool.tool_name,
            description = tool.description,
            version = tool.version,
            types = ["galaxy_shed", "git_harvested"],
            tags = tool.categories,
            input_slots = inputs,
            output_slots = outputs,
            created_by = "harvester"
        )


    session.add(shed_generic)
    session.commit()

    logger.info(f"Added tool '{shed_generic.id}' to the database with URI: {shed_generic.uri}")

