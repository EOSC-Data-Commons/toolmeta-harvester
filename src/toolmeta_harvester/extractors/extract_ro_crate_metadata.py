"""
Backward compatibility module.

Prefer imports from:
    toolmeta_harvester.extractors.ro_crate
"""

from toolmeta_harvester.extractors.ro_crate import (
    build_entity_index,
    extract_profiles,
    extract_ro_crate_metadata,
    get_main_entity,
    get_rocrate_version,
    get_root_entity,
    is_ro_crate,
    ro_crate_defines_tool,
    resolve,
)

__all__ = [
    "build_entity_index",
    "extract_profiles",
    "extract_ro_crate_metadata",
    "get_main_entity",
    "get_rocrate_version",
    "get_root_entity",
    "is_ro_crate",
    "ro_crate_defines_tool",
    "resolve",
]
