import logging
from toolmeta_harvester.adaptors import galaxy_toolshed as shed

logger = logging.getLogger(__name__)

# SHED_TOOL_URI= "toolshed.g2.bx.psu.edu/repos/iuc/fastp/fastp/0.19.5+galaxy1"
SHED_TOOL_URI = "toolshed.g2.bx.psu.edu/repos/iuc/biapy/biapy/3.6.8+galaxy0"

def main():
    # tool_info = shed.fetch_tool_meta_from_shed_api(SHED_TOOL_URI)
    # logger.info(tool_info)
    tool = shed.fetch_toolshed_tool(SHED_TOOL_URI)
    logger.info(f"Tool Name: {tool.tool_name}")
    logger.info(f"Tool Version: {tool.version}")
    logger.info(f"Tool Description: {tool.description}")
    logger.info(f"Tool URL: {tool.uri}")
    logger.info(f"Tool help: {tool.help}")
    for input in tool.inputs:
        logger.info(f"Input Name: {input}")
        # logger.info(f"Input Type: {input.format}")
        # logger.info(f"Input Description: {input.description}")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
