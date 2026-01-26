import logging
from toolmeta_harvester.tasks import galaxy_harvest_tasks as ght
from toolmeta_harvester.adaptors import galaxy_workflow_hub as gwh

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s: %(message)s",
)


def pipeline_one():
    # Step 1: Initialize DB
    ght.create_tables()
    session = ght.get_db_session()
    logging.info("Database tables created.")

    # Step 2: Crawl Galaxy Workflow Hub
    # Get first n workflows from Galaxy Workflow Hub
    number_of_wf_to_harvest = 1
    # Iterate through Galaxy Workflow Hub workflows and print their metadata
    for workflow_info in gwh.iter_workflows():
        print(f"Workflow UUID: {workflow_info.uuid}")
        print(f"Name: {workflow_info.name}")
        print(f"Version: {workflow_info.version}")
        print(f"Description: {workflow_info.description}")
        print(f"Tags: {', '.join(workflow_info.tags)}")
        print(f"URL: {workflow_info.url}")
        print(f"Input data types: {len(workflow_info.inputs)}")
        print(f"Output data types: {len(workflow_info.outputs)}")
        print(f"Toolshed tools used: {len(workflow_info.toolshed_tools)}")
        print(workflow_info.toolshed_tools)
        print("-" * 40)

        # Step 3: Store Input/Ouput toolshed tools in DB
        for tool in workflow_info.input_tools + workflow_info.output_tools:
            ght.add_tool_to_db(tool, session)
            print(f"Added tool {tool.tool_name} to the database.")
        # Step 4: Store Galaxy Workflow in DB
        ght.add_workflow_to_db(workflow_info, session)
        print("Added workflow and tools to the database.")

        number_of_wf_to_harvest -= 1
        if number_of_wf_to_harvest == 0:
            break
