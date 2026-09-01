# toolmeta_harvester/flows/loader.py


def load_flows() -> None:
    from toolmeta_harvester.flows import harvest_github  # noqa: F401
    from toolmeta_harvester.flows import harvest_workflowhub  # noqa: F401
    from toolmeta_harvester.flows import harvest_zenodo  # noqa: F401
    from toolmeta_harvester.flows import harvest_bioschemas  # noqa: F401
    from toolmeta_harvester.flows import harvest_rsd  # noqa: F401
