import requests
import requests_cache
import json
from dataclasses import dataclass
from pathlib import Path
import zipfile
import io
from toolmeta_harvester.adaptors import galaxy_toolshed as shed

TOOLShed = "https://toolshed.g2.bx.psu.edu"
# BASE_URL = "http://usegalaxy.org/api"
WORKFLOW_HUB_API = "https://workflowhub.eu/ga4gh/trs/v2/"



# CACHE_FILE = "cache/usegalaxy_org_registry.json"
HUB_CACHE_FILE = "cache/workflowhub_registry.json"

HEADERS = {
    "Accept": "application/json",
}

# Initialize requests cache 
requests_cache.install_cache('workflowhub_org_cache', 
                             backend='sqlite',
                             expire_after=86400)

# @dataclass(frozen=True)
# class ToolInfo:
#     id: str
#     tool_name: str
#     version: str
#     inputs: list
#     outputs: list
#     command: str
#     repo_url: str
#     raw: str
#     raw_format: str = "json"
#     tool_type: str = "galaxy_workflow"


def get_json(url, result=None):
    if not result:
        result = []
    r = requests.get(url, timeout=30, headers=HEADERS)
    r.raise_for_status()
    result.extend(r.json())
    next_page = r.headers.get("next_page", None)
    if next_page:
        get_json(next_page, result)

    return result

def save_json(data, filename):
    with open(filename, "w") as f:
        json.dump(data, f, indent=2)

def load_json(filename):
    with open(filename, "r") as f:
        return json.load(f)

def is_cached(filename):
    return Path(filename).is_file()

def fetch_text_file(url):
    r = requests.get(url, timeout=30, headers=HEADERS)
    r.raise_for_status()
    return r.text

def retrieve_json(url, cache_file, use_cache=True):
    if use_cache and is_cached(cache_file):
        print("Loading registry from cache...")
        return load_json(cache_file)
    workflows = get_json(url)
    save_json(workflows, cache_file)
    return workflows

def extract_galaxy_workflow_from_zip(url):
    response = requests.get(url, timeout=30)
    response.raise_for_status()

    # Open ZIP in memory
    with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
        ga_files = [name for name in zf.namelist() if name.endswith(".ga")]

        if not ga_files:
            raise ValueError("No .ga Galaxy workflow file found in ZIP")

        # Take the first .ga file
        ga_name = ga_files[0]

        with zf.open(ga_name) as ga_file:
            return json.load(ga_file)

def get_hub_workflows(type=None):
    workflows = retrieve_json(f"{WORKFLOW_HUB_API}/tools/", HUB_CACHE_FILE, True)
    if not type:
        return workflows
    results = []
    for w in workflows:
        workflow_types = w['versions'][0]['descriptor_type']
        workflow_type = workflow_types[0].lower() if len(workflow_types) > 0 else None
        if workflow_type != type.lower():
            continue
        results.append(w)
    return results

def get_ga_workflow(w):
    download_url = f"{w['url']}/download"
    ga_workflow = extract_galaxy_workflow_from_zip(download_url)
    return ga_workflow 

def infer_input_datatype(step: dict) -> str | None:
    outputs = step.get("outputs", [])
    if not outputs:
        return None
    return outputs[0].get("type")

def get_step_shed_tools(ga):
    steps = ga.get("steps", {})
    tools = []
    for step_id, step in steps.items():
        step_type = step.get("type")
        if step_type == 'tool':
            tool_id = step.get("tool_id")
            # print(tool_id)
            if tool_id.startswith("toolshed"):
                tools.append(tool_id)
                tool_version = step.get("tool_version")
                # print(f"{tool_id}, {tool_version}")
    return tools

def get_shed_tool_name(tool_id: str) -> str:
    """
    Extract ToolShed tool name from Galaxy tool_id.
    Example tool_id: toolshed.g2.bx.psu.edu/repos/devteam/bwa_mem/bwa_mem/
    """
    parts = tool_id.split("/")
    if not tool_id.startswith("toolshed."):
        raise ValueError("Not a ToolShed tool_id")
    # repo_name = parts[3]
    tool_name = parts[4]
    # revision = parts[-1]
    return tool_name

def fetch_toolshed_tool(tool_id: str) -> dict:
    """
    Fetch ToolShed tool metadata (including wrapper XML) given a Galaxy tool_id.
    """
    parts = tool_id.split("/")
    if not tool_id.startswith("toolshed."):
        raise ValueError("Not a ToolShed tool_id")

    # host = parts[0].replace("toolshed.", "")
    host = parts[0]
    owner = parts[2]
    repo = parts[3]
    revision = parts[-1]

    url = f"https://{host}/api/repositories/get_repository_revision_install_info"
    params = {
        "name": repo,
        "owner": owner,
        "changeset_revision": revision,
    }

    r = requests.get(url, params=params, timeout=30)
    r.raise_for_status()
    return r.json()

def get_tools_connected_to_inputs(ga):
    inputs = get_inputs(ga)
    input_step_ids = [inp['step_id'] for inp in inputs]
    steps = ga.get("steps", {})
    input_tools = []
    for step_id, step in steps.items():
        step_type = step.get("type")
        if step_type == 'tool':
            input_connections = step.get("input_connections", {})
            for input_name, connection in input_connections.items():
                conn_id = str(connection['id'])
                if conn_id in input_step_ids:
                    input_tools.append(step.get("content_id"))

    return input_tools

def get_outputs(ga):
    steps = ga.get("steps", {})
    outputs = []
    ref_step_ids = {}
    for s_id in list(steps.keys()):
        ref_step_ids[s_id] = 0
    for step_id, step in steps.items():
        input_connections = step.get("input_connections", {})
        for input_name, connection in input_connections.items():
            conn_id = str(connection['id'])
            if conn_id in ref_step_ids:
                ref_step_ids[conn_id] += 1
    for step_id, step in steps.items():
        if ref_step_ids[step_id] == 0:
            outputs.append({
                "step_id": step_id,
                "name": step.get("name"),
                "label": step.get("label"),
                "data_type": step.get("type"),
                "tool_id": step.get("content_id", ""),
            })
    return outputs

def get_shed_outputs(ga):
    outputs_steps = get_outputs(ga)
    output_tools = []
    seen = set()
    for output in outputs_steps:
        tool_id = output.get("tool_id", "")
        tool_name = get_shed_tool_name(tool_id)
        # print(f"Output tool id: {tool_id}, name: {tool_name}")
        if tool_name in seen:
            continue
        tool_meta = fetch_toolshed_tool(tool_id)[0]
        # print(f"Tool meta: {tool_meta}")
        repo_api_url = shed.convert_git_url_to_api(tool_meta['remote_repository_url'])
        tools = shed.crawl_repository(repo_api_url)
        for tool in tools:
            if tool.id == tool_name:
                output_tools.append(tool)
                seen.add(tool_name)
                break
    return output_tools


def get_inputs(ga):
    steps = ga.get("steps", {})
    inputs = []

    for step_id, step in steps.items():
        step_type = step.get("type")
        if step_type in {"data_input", "data_collection_input", "parameter_input"}:
            inputs.append({
                "step_id": step_id,
                "name": step.get("name"),
                "label": step.get("label"),
                "data_type": step.get("type"),
                "optional": step.get("optional", False),
            })

    return inputs

def get_shed_inputs(ga):
    input_tool_ids = get_tools_connected_to_inputs(ga)
    input_tools = []
    seen = set()
    for tool_id in input_tool_ids:
        tool_name = get_shed_tool_name(tool_id)
        if tool_name in seen:
            continue
        tool_meta = fetch_toolshed_tool(tool_id)[0]
        repo_api_url = shed.convert_git_url_to_api(tool_meta['remote_repository_url'])
        tools = shed.crawl_repository(repo_api_url)
        for tool in tools:
            if tool.id == tool_name:
                input_tools.append(tool)
                seen.add(tool_name)
                break
    return input_tools

def test():
    workflows = get_hub_workflows(type="galaxy")
    print(f"Found {len(workflows)} Galaxy workflows on WorkflowHub")
    for wf in workflows:
        ga_w = get_ga_workflow(wf)
        input_tools = get_shed_inputs(ga_w)
        for tool in input_tools:
            print(f"- {tool.id} ({tool.version})") 
            print(f"Inputs: {tool.inputs}")
            # print(tool)
        output_tools = get_shed_outputs(ga_w)
        for tool in output_tools:
            print(f"+ {tool.id} ({tool.version})") 
            print(f"Outputs: {tool.outputs}")
            # print(tool)
        break
        
test()
