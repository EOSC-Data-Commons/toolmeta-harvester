#!/usr/bin/env python3

import toolmeta_harvester.flows.harvest_zenodo  # noqa: F401
import toolmeta_harvester.flows.harvest_github  # noqa: F401
import toolmeta_harvester.flows.harvest_bioschemas  # noqa: F401
import toolmeta_harvester.flows.harvest_workflowhub  # noqa: F401
import toolmeta_harvester.flows.harvest_rsd  # noqa: F401

from toolmeta_harvester.flows.registry import (
    get_flows,
)


def main() -> None:
    flows = get_flows()

    for flow in flows:
        print(f"- {flow.name} ({flow.kind})")
        print(f"      schedule: {flow.default_schedule}")
        print(f"      handler:  {flow.handler.__name__}")
        print("--------------------------------")


if __name__ == "__main__":
    main()
