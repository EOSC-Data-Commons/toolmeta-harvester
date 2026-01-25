import logging
from toolmeta_harvester.adaptors import galaxy_toolshed as shed

logger = logging.getLogger(__name__)

class WorkflowInfo:
    uuid: str
    name: str
    description: str
    url: str
    version: str
    tags: list = []
    inputs: list = []
    outputs: list = []
    steps: list = []
    toolshed_tools: list = []

def get_step_shed_tools(ga):
    steps = ga.get("steps", {})
    tools = []
    for step_id, step in steps.items():
        step_type = step.get("type")
        if step_type.lower() == 'tool':
            tool_id = step.get("tool_id") or step.get("content_id")
            if tool_id.startswith("toolshed"):
                tools.append(tool_id)
    return tools

def get_shed_tool_name(tool_id: str) -> str:
    """
    Extract ToolShed tool name from Galaxy tool_id.
    Example tool_id: toolshed.g2.bx.psu.edu/repos/devteam/bwa_mem/bwa_mem/
    """
    parts = tool_id.split("/")
    if not tool_id.startswith("toolshed."):
        raise ValueError(f"Not a ToolShed tool_id: {tool_id}")
    tool_name = parts[4]
    # repo_name = parts[3]
    # revision = parts[-1]
    return tool_name

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
                    input_tools.append(step.get("tool_id") or step.get("content_id"))

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
                "tool_id": step.get("content_id") or step.get("tool_id"),
            })
    return outputs

def get_shed_outputs(ga):
    outputs_steps = get_outputs(ga)
    output_tools = []
    seen = set()
    for output in outputs_steps:
        tool_id = output.get("tool_id", "")
        try:
            tool_name = get_shed_tool_name(tool_id)
            if tool_name in seen:
                continue
            tool_meta = shed.fetch_toolshed_tool(tool_id)[0]
            repo_api_url = shed.convert_git_url_to_api(tool_meta['remote_repository_url'])
            if not repo_api_url:
                logger.warning(f"Could not convert git URL to API URL: {tool_meta['remote_repository_url']}")
                continue
            # tools = shed.crawl_repository(repo_api_url)
            for url, tools in shed.smart_crawl_repository_iter(repo_api_url):
                for tool in tools:
                    if tool.id == tool_name:
                        output_tools.append(tool)
                        seen.add(tool_name)
                        break
                # Break outer loop once tool is found
                if tool_name in seen:
                    break
        except Exception:
            logger.exception(f"Retrieving output shed tool: {tool_id}, skipping...")
            continue
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
        try:
            tool_name = get_shed_tool_name(tool_id)
            if tool_name in seen:
                continue
            tool_meta = shed.fetch_toolshed_tool(tool_id)[0]
            repo_api_url = shed.convert_git_url_to_api(tool_meta['remote_repository_url'])
            # tools = shed.crawl_repository(repo_api_url)
            for url, tools in shed.smart_crawl_repository_iter(repo_api_url):
                for tool in tools:
                    if tool.id == tool_name:
                        input_tools.append(tool)
                        seen.add(tool_name)
                        break
                # Break outer loop once tool is found
                if tool_name in seen:
                    break
        except Exception:
            logger.exception(f"Retrieving input shed tool: {tool_id}, skipping...")
            continue
    return input_tools

def parse_workflow(ga) -> WorkflowInfo:
    wf_info = WorkflowInfo()
    wf_info.uuid = ga.get("uuid", "")
    wf_info.name = ga.get("name", "")
    wf_info.version = ga.get("version", '')
    wf_info.tags = ga.get("tags", [])
    wf_info.description = ga.get("description", "")
    wf_info.toolshed_tools = get_step_shed_tools(ga)

    input_tools = get_shed_inputs(ga)
    for tool in input_tools:
        for input in tool.inputs:
            wf_info.inputs.append(input)
    output_tools = get_shed_outputs(ga)
    for tool in output_tools:
        for output in tool.outputs:
            wf_info.outputs.append(output)

    return wf_info

