from __future__ import annotations

from typing import Any

from toolmeta_harvester.extractors.codemeta import (
    extract_codemeta_metadata,
    is_codemeta,
)
from toolmeta_harvester.extractors.jsonld import (
    extract_jsonld_metadata,
)
from toolmeta_harvester.extractors.ro_crate import (
    extract_ro_crate_metadata,
    is_ro_crate,
)
from toolmeta_harvester.extractors.bioschemas import (
    extract_bioschemas_metadata,
    is_bioschemas,
)


def extract_tool_metadata(
    metadata: dict[str, Any],
) -> dict[str, Any]:
    """
    Extract canonical ScienceToolMeta from supported metadata.

    Detection precedence:

        RO-Crate
        CodeMeta
        generic schema.org / JSON-LD
    """

    if not isinstance(metadata, dict):
        raise TypeError("Metadata must be a dictionary")

    if is_ro_crate(metadata):
        return extract_ro_crate_metadata(metadata)

    if is_codemeta(metadata):
        return extract_codemeta_metadata(metadata)

    if is_bioschemas(metadata):
        return extract_bioschemas_metadata(metadata)

    return extract_jsonld_metadata(metadata)
