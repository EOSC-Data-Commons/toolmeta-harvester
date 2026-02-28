import logging
from toolmeta_harvester.tasks import galaxy_harvest_tasks as ght
from toolmeta_harvester.adaptors import galaxy_workflow_hub as gwh

logger = logging.getLogger(__name__)


def pipeline_harvest_workflow_hub(no_of_workflows: int = 10):
    # Step 1: Initialize DB
    ght.create_tables()
    session = ght.get_db_session()
    logger.info("Database tables created.")

    # Step 2: Crawl Galaxy Workflow Hub
    # Get first n workflows from Galaxy Workflow Hub
    number_of_wf_to_harvest = 0
    # Iterate through Galaxy Workflow Hub workflows and print their metadata
    for workflow_info in gwh.iter_workflows():
        logger.info(f"Workflow UUID: {workflow_info.uuid}")
        logger.info(f"Name: {workflow_info.name}")
        logger.info(f"Version: {workflow_info.version}")
        # logger.info(f"Description: {workflow_info.description}")
        logger.info(f"Tags: {', '.join(workflow_info.tags)}")
        logger.info(f"URL: {workflow_info.url}")
        logger.info(f"Input data types: {len(workflow_info.inputs)}")
        logger.info(f"Output data types: {len(workflow_info.outputs)}")
        logger.info(f"Toolshed tools used: {
                    len(workflow_info.toolshed_tools)}")
        logger.info(workflow_info.toolshed_tools)
        logger.info("-" * 40)

        # Step 3: Store Galaxy Workflow in DB
        # ght.add_workflow_to_db(workflow_info, session)
        ght.add_workflow_to_generic_table(workflow_info, session)
        logger.info("Added workflow and tools to the database.")

        number_of_wf_to_harvest += 1
        if number_of_wf_to_harvest == no_of_workflows:
            logger.info(
                f"Harvested {
                    number_of_wf_to_harvest
                } workflows from Galaxy Workflow Hub. Stopping harvest."
            )
            break
