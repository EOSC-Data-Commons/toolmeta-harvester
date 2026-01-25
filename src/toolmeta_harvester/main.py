import logging
from toolmeta_harvester.adaptors import galaxy_workflow_hub as gwh

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s: %(message)s",
)

def main():
    # Get first n workflows from Galaxy Workflow Hub
    number_of_wf_to_harvest = 5
    # Iterate through Galaxy Workflow Hub workflows and print their metadata
    for workflow_info in gwh.iter_workflows():
        print(f"Workflow UUID: {workflow_info.uuid}")
        print(f"Name: {workflow_info.name}")
        print(f"Version: {workflow_info.version}")
        print(f"Description: {workflow_info.description}")
        print(f"Tags: {', '.join(workflow_info.tags)}")
        print(f"URL: {workflow_info.url}")
        print(f"Toolshed tools used: {len(workflow_info.toolshed_tools)}")
        print(f"Input data types: {len(workflow_info.inputs)}")
        print(f"Output data types: {len(workflow_info.outputs)}")
        print("-" * 40)

        number_of_wf_to_harvest -= 1
        if number_of_wf_to_harvest == 0:
            break


if __name__ == "__main__":
    main()

