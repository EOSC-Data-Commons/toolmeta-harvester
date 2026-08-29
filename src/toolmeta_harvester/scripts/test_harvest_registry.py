#!/usr/bin/env python3

import toolmeta_harvester.flows.harvest_zenodo  # noqa: F401

from toolmeta_harvester.flows.registry import (
    get_dynamic_harvests,
    get_flow,
)


def main() -> None:
    flow = get_flow("zenodo")

    assert flow.name == "zenodo"
    assert flow.kind == "dynamic"
    assert flow.handler.__name__ == "pipeline_harvest_zenodo"

    print("Zenodo flow registration OK")
    print(f"name:     {flow.name}")
    print(f"kind:     {flow.kind}")
    print(f"schedule: {flow.default_schedule}")
    print(f"handler:  {flow.handler.__name__}")

    print("\nRegistered dynamic harvests:")
    for registered_flow in get_dynamic_harvests():
        print(f"- {registered_flow.name} ({registered_flow.default_schedule})")


if __name__ == "__main__":
    main()
