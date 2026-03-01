import logging
from pathlib import Path
from toolmeta_harvester.flows import harvest_galaxy_hub_workflows as gwh

LOG_FILE = Path("logs/harvest_galaxy_hub_workflows.log")
# Create directory if it does not exist
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s: %(message)s",
    handlers=[logging.StreamHandler(),
              logging.FileHandler(LOG_FILE)],
)

logger = logging.getLogger(__name__)


def main():
    logger.info("Starting Galaxy Hub workflow harvesting process.")
    gwh.pipeline_harvest_workflow_hub(5)


if __name__ == "__main__":
    main()
