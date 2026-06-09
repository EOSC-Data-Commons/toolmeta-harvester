import logging
from pathlib import Path
from toolmeta_harvester.config import load_git_config
from toolmeta_harvester.flows import harvest_usegalaxy_base as galaxy_base

LOG_FILE = Path("logs/harvest_usegalaxy_ch.log")
# Create directory if it does not exist
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s: %(message)s",
    handlers=[logging.StreamHandler(),
              logging.FileHandler(LOG_FILE)],
)

logger = logging.getLogger(__name__)

GALAXY_INSTANCE_URL = "https://usegalaxy.ch/"


def main():
    git_config = load_git_config()
    if not git_config.api_key:
        logger.error("GitHub API key not found in configuration. Please set it up before running the harvester.")
        return
    logger.info(f"Starting Galaxy {GALAXY_INSTANCE_URL} workflow harvesting process.")
    galaxy_base.pipeline_harvest_workflows(-1, GALAXY_INSTANCE_URL)


if __name__ == "__main__":
    main()
