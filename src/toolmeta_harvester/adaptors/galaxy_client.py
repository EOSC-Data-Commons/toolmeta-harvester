from bioblend.galaxy import GalaxyInstance
from toolmeta_harvester.config import load_galaxy_config
from toolmeta_harvester.adaptors import galaxy_workflow as hub

GALAXY_CONFIG = load_galaxy_config()
GALAXY_URL = GALAXY_CONFIG.host_url
API_KEY = GALAXY_CONFIG.api_key

gi = GalaxyInstance(url=GALAXY_URL, key=API_KEY)

# Test the connection
print(f"Connected to {GALAXY_URL}, version: {gi.config.get_version()}")

# workflows = hub.get_hub_workflows(type="galaxy")
# for w in workflows:
#     ga_w = hub.get_ga_workflow(w)
#     # workflow = gi.workflows.import_workflow_dict(ga_w)
#     shed_tools = hub.get_step_shed_tools(ga_w)
#     print(shed_tools)
#     # workflow_id = workflow["id"]
#     # tools = gi.workflows.show_workflow(workflow_id)["steps"]
#     # for step_id, step in tools.items():
#     #     tool_id = step["tool_id"]
#     #
#     #     # Get resolved IO for that tool
#     #     tool_info = gi.tools.show_tool(tool_id, io_details=True)
#     #     print(tool_info)
#     #
#         # print(tool_id, tool_info["inputs"], tool_info["outputs"])
#     break

def extract_data_inputs(tool_inputs):
    data_inputs = []

    def recurse(inputs):
        for inp in inputs:
            print(inp)
            if inp["type"] in ("data", "data_collection"):
                data_inputs.append({
                    "name": inp["name"],
                    "type": inp["type"],
                    "extensions": inp.get("extensions"),
                    "collection_types": inp.get("collection_types"),
                })

            # recurse into nested structures
            if inp["type"] in ("conditional", "section"):
                if inp["type"] == "conditional":
                    for case in inp.get("cases", []):
                        recurse(case.get("inputs", []))
                else:
                    recurse(inp.get("inputs", []))

    recurse(tool_inputs)
    return data_inputs

def extract_outputs(tool_outputs):
    outputs = []

    for o in tool_outputs:
        outputs.append({
            "name": o.get("name"),
            "type": o.get("output_type"),
            "format": o.get("format"),
            "label": o.get("label"),
            "hidden": o.get("hidden", False),
        })

    return outputs

workflows = gi.workflows.get_workflows()
for w in workflows:
    print(w["id"])
    workflow_id = w['id']
    tools = gi.workflows.show_workflow(workflow_id)["steps"]
    tool_info = gi.tools.show_tool("fastp", io_details=True)
    tool_inputs = extract_data_inputs(tool_info["inputs"])
    tool_outputs = extract_outputs(tool_info["outputs"])
    
    # print(tool_inputs)
    # print()
    # print(tool_outputs)
    # print(tool_info)
    # print(tool_info["inputs"], tool_info["outputs"])
    # for step_id, step in tools.items():
    #     tool_id = step["tool_id"]
    #   
    #     # tool_info = gi.tools.show_tool(tool_id, io_details=True)
    #     tool_info = gi.tools.show_tool(tool_id)
    #     print(tool_info)
    #     print("########################################################")
    #     print()
      
        # print(tool_id, tool_info["inputs"], tool_info["outputs"])


