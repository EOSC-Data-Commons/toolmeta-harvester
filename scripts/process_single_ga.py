import logging
from toolmeta_harvester.adaptors import galaxy_workflow_hub as gwh
from toolmeta_harvester.adaptors import galaxy_workflow as ga_workflow

logger = logging.getLogger(__name__)

WORKFLOW_HUB_URL = "https://workflowhub.eu/workflows/123"
# WORKFLOW_HUB_URL = "https://workflowhub.eu/workflows/685" # Auth error

def main():
    logger.info(f"Fetching workflow from {WORKFLOW_HUB_URL}...")
    ga_w = gwh.extract_galaxy_workflow_from_zip(f"{WORKFLOW_HUB_URL}/download")
    workflow_info = ga_workflow.parse_workflow(ga_w)
    logger.info(f"Workflow name: {workflow_info.name}")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
