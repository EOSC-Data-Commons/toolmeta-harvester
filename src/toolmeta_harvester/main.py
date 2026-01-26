import logging
from toolmeta_harvester.flows import harvest_galaxy_hub_workflows as gwh

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s: %(message)s",
)


def main():
    gwh.pipeline_one()


if __name__ == "__main__":
    main()
