from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal


HarvestKind = Literal["dynamic", "static"]


@dataclass(frozen=True)
class HarvestFlow:
    name: str
    kind: HarvestKind
    handler: Callable[..., Any]
    default_schedule: str | None = None


_registry: dict[str, HarvestFlow] = {}


def register_flow(flow: HarvestFlow) -> None:
    if flow.name in _registry:
        raise ValueError(f"Harvest flow '{flow.name}' is already registered")

    _registry[flow.name] = flow


def get_flow(name: str) -> HarvestFlow:
    return _registry[name]


def get_dynamic_flows() -> list[HarvestFlow]:
    from toolmeta_harvester.flows.loader import load_flows

    load_flows()
    return [flow for flow in _registry.values() if flow.kind == "dynamic"]


def get_static_flows() -> list[HarvestFlow]:
    from toolmeta_harvester.flows.loader import load_flows

    load_flows()
    return [flow for flow in _registry.values() if flow.kind == "static"]


def get_flows() -> list[HarvestFlow]:
    return list(_registry.values())
