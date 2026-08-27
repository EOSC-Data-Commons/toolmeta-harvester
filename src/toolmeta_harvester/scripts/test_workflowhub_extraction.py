from __future__ import annotations

import argparse
import json
from datetime import date, datetime
from uuid import UUID

from toolmeta_harvester.extractors.tool_metadata import (
    extract_tool_metadata,
)
from toolmeta_harvester.tasks.workflowhub_rocrate import (
    download_rocrate,
    get_hub_workflows,
)


def json_default(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()

    if isinstance(value, UUID):
        return str(value)

    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def get_workflow_by_id(
    workflow_id: str,
) -> dict:
    workflows = get_hub_workflows(use_cache=True)

    for workflow in workflows:
        if str(workflow.get("id")) == str(workflow_id):
            return workflow

    raise ValueError(f"WorkflowHub workflow {workflow_id} not found")


def test_workflowhub_extraction(
    workflow_id: str,
) -> None:
    workflow = get_workflow_by_id(workflow_id)

    crate = download_rocrate(workflow)

    metadata = extract_tool_metadata(crate)

    print(
        json.dumps(
            metadata,
            indent=2,
            ensure_ascii=False,
            default=json_default,
        )
    )


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Fetch a WorkflowHub RO-Crate and print normalized ScienceToolMeta JSON"
        )
    )

    parser.add_argument(
        "workflow_id",
        help="WorkflowHub workflow ID",
    )

    args = parser.parse_args()

    test_workflowhub_extraction(args.workflow_id)


if __name__ == "__main__":
    main()
