from collections.abc import Callable
from typing import Any

from toolmeta_harvester.flows.registry import (
    HarvestFlow,
    register_flow,
)


def dynamic_harvest(
    *,
    name: str,
    hosts: list[str],
    default_schedule: str | None = None,
):
    def decorator(func: Callable[..., Any]):
        register_flow(
            HarvestFlow(
                name=name,
                kind="dynamic",
                handler=func,
                default_schedule=default_schedule,
                hosts=tuple(hosts),
            )
        )

        return func

    return decorator


def static_harvest(
    *,
    name: str,
    default_schedule: str | None = None,
):
    def decorator(func: Callable[..., Any]):
        register_flow(
            HarvestFlow(
                name=name,
                kind="static",
                handler=func,
                default_schedule=default_schedule,
            )
        )

        return func

    return decorator
