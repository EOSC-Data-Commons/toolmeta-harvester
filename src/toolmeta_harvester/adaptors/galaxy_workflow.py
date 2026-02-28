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
    input_formats: list = []
    output_formats: list = []
    input_tools: list = []
    output_tools: list = []
    steps: list = []
    toolshed_tools: list = []


def get_step_shed_tools(ga):
    steps = ga.get("steps", {})
    tools = []
    for step_id, step in steps.items():
        step_type = step.get("type")
        if step_type.lower() == "tool":
            tool_id = step.get("tool_id") or step.get("content_id")
            if tool_id.startswith("toolshed"):
                tools.append(tool_id)
    return tools


def is_shed_uri(tool_id: str) -> bool:
    if not tool_id:
        return False
    return tool_id.startswith("toolshed.")


def get_tools_connected_to_inputs(ga):
    inputs = get_inputs(ga)
    input_step_ids = [inp["step_id"] for inp in inputs]
    steps = ga.get("steps", {})
    input_tools = []
    for step_id, step in steps.items():
        step_type = step.get("type")
        if step_type == "tool":
            input_connections = step.get("input_connections", {})
            for input_name, connection in input_connections.items():
                if isinstance(connection, list):
                    for c in connection:
                        conn_id = str(c["id"])
                        if conn_id in input_step_ids:
                            input_tools.append(step.get("tool_id")
                                               or step.get("content_id"))
                else:
                    conn_id = str(connection["id"])
                    if conn_id in input_step_ids:
                        input_tools.append(step.get("tool_id")
                                        or step.get("content_id"))

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
            if isinstance(connection, list):
                for c in connection:
                    conn_id = str(c["id"])
                    if conn_id in ref_step_ids:
                        ref_step_ids[conn_id] += 1
            else:
                conn_id = str(connection["id"])
                if conn_id in ref_step_ids:
                    ref_step_ids[conn_id] += 1
    for step_id, step in steps.items():
        if ref_step_ids[step_id] == 0:
            outputs.append(
                {
                    "step_id": step_id,
                    "name": step.get("name"),
                    "label": step.get("label"),
                    "data_type": step.get("type"),
                    "tool_id": step.get("content_id") or step.get("tool_id"),
                }
            )
    return outputs


def get_shed_outputs(ga):
    outputs_steps = get_outputs(ga)
    output_tools = []
    seen = set()
    for output in outputs_steps:
        tool_id = output.get("tool_id", "")
        if not is_shed_uri(tool_id):
            logger.debug(f"Output tool_id not from ToolShed: {
                         tool_id}, skipping...")
            continue
        # Will refer to ids with format toolshed.g2.bx.psu.edu/... as tool_uri
        tool_uri = tool_id
        if tool_uri in seen:
            continue
        try:
            tool = shed.fetch_toolshed_tool(tool_uri)
            if tool:
                output_tools.append(tool)
                seen.add(tool_uri)
                continue
        except Exception:
            logger.warning(f"Error retrieving output shed tool: {
                             tool_uri}, skipping...")
            continue
    return output_tools


def get_inputs(ga):
    steps = ga.get("steps", {})
    inputs = []

    for step_id, step in steps.items():
        step_type = step.get("type")
        if step_type in {"data_input", "data_collection_input", "parameter_input"}:
            # logger.info(step)
            inputs.append(
                {
                    "step_id": step_id,
                    "name": step.get("name"),
                    "label": step.get("label"),
                    "data_type": step.get("type"),
                    "optional": step.get("optional", False),
                }
            )

    return inputs


def get_shed_inputs(ga):
    input_tool_ids = get_tools_connected_to_inputs(ga)
    input_tools = []
    seen = set()
    for tool_id in input_tool_ids:
        if not is_shed_uri(tool_id):
            logger.debug(f"Input tool_id not from ToolShed: {
                         tool_id}, skipping...")
            continue
        tool_uri = tool_id
        if tool_uri in seen:
            continue
        try:
            tool = shed.fetch_toolshed_tool(tool_uri)
            if tool:
                input_tools.append(tool)
                seen.add(tool_uri)
                logger.debug(f"Added input tool: {tool}")
                continue
        except Exception:
            logger.warning(f"Error retrieving input shed tool: {
                             tool_uri}, skipping...")
            continue
    return input_tools


def parse_workflow(ga) -> WorkflowInfo:
    wf_info = WorkflowInfo()
    wf_info.uuid = ga.get("uuid", "")
    wf_info.name = ga.get("name", "")
    wf_info.version = ga.get("version", "")
    wf_info.tags = ga.get("tags", [])
    wf_info.raw_ga = ga
    wf_info.description = ga.get("description", "")
    wf_info.toolshed_tools = get_step_shed_tools(ga)

    input_tools = get_shed_inputs(ga)
    wf_info.input_tools = input_tools
    input_formats = set()
    for tool in input_tools:
        for input in tool.inputs:
            wf_info.inputs.append(input)
        formats = shed.extract_formats_from_tool(tool)
        input_formats.update(formats)
    wf_info.input_formats = list(input_formats)

    # # The inputs in the DAG are usually stubs that link to nodes with actual tools
    # input_steps = get_inputs(ga)
    # for step in input_steps:
    #     data_type = step.get("data_type")
    #     if data_type:
    #         input_formats.add(data_type.lower())
    # wf_info.input_formats = list(input_formats)

    output_tools = get_shed_outputs(ga)
    wf_info.output_tools = output_tools
    output_formats = set()
    for tool in output_tools:
        for output in tool.outputs:
            wf_info.outputs.append(output)
        formats = shed.extract_formats_from_tool(tool)
        output_formats.update(formats)
    wf_info.output_formats = list(output_formats)

    return wf_info
