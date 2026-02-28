import logging
from toolmeta_harvester.flows import harvest_galaxy_hub_workflows as gwh

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(name)s %(levelname)s: %(message)s",
)

logger = logging.getLogger(__name__)


def main():
    logger.info("Starting Galaxy Hub workflow harvesting process.")
    gwh.pipeline_harvest_workflow_hub(1)


if __name__ == "__main__":
    main()
