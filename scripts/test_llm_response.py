import asyncio
from toolmeta_harvester.config import egi_llm_api_key, llm_api
from toolmeta_harvester.tasks.enrichment.llm import enrich_tool_metadata
from toolmeta_harvester.tasks.enrichment.prompts.generation import (
    MODEL,
    PROMPT_VERSION,
)


LLM_API = llm_api()
EGI_LLM_API_KEY = egi_llm_api_key()


raw_metadata = """{
        "cost": null,
        "link": [],
        "name": "nanoranger",
        "owner": "pub2tools2024",
        "topic": [
            {
                "uri": "http://edamontology.org/topic_0625",
                "term": "Genotype and phenotype"
            },
            {
                "uri": "http://edamontology.org/topic_3512",
                "term": "Gene transcripts"
            },
            {
                "uri": "http://edamontology.org/topic_4028",
                "term": "Single-cell sequencing"
            },
            {
                "uri": "http://edamontology.org/topic_2830",
                "term": "Immunoproteins and antigens"
            },
            {
                "uri": "http://edamontology.org/topic_3308",
                "term": "Transcriptomics"
            }
        ],
        "credit": [
            {
                "url": null,
                "name": "Catherine J. Wu",
                "note": null,
                "email": "catherine_wu@dfci.harvard.edu",
                "rorid": null,
                "gridid": null,
                "orcidid": null,
                "typeRole": [],
                "fundrefid": null,
                "typeEntity": "Person"
            }
        ],
        "license": null,
        "otherID": [],
        "version": [],
        "download": [],
        "function": [
            {
                "cmd": null,
                "note": null,
                "input": [],
                "output": [],
                "operation": [
                    {
                        "uri": "http://edamontology.org/operation_3196",
                        "term": "Genotyping"
                    },
                    {
                        "uri": "http://edamontology.org/operation_3227",
                        "term": "Variant calling"
                    },
                    {
                        "uri": "http://edamontology.org/operation_0308",
                        "term": "PCR primer design"
                    },
                    {
                        "uri": "http://edamontology.org/operation_0314",
                        "term": "Gene expression profiling"
                    }
                ]
            }
        ],
        "homepage": "https://github.com/mehdiborji/nanoranger",
        "language": [],
        "maturity": null,
        "relation": [],
        "toolType": [],
        "validated": 0,
        "biotoolsID": "nanoranger",
        "elixirNode": [],
        "lastUpdate": "2026-01-14T07:17:23.620981Z",
        "description": "Nanoranger is a long-read sequencing workflow and analysis pipeline for detecting cell lineage-defining features like single-nucleotide variants and fusion genes, particularly suited for cancer and immune phenotype analysis.",
        "publication": [
            {
                "doi": "10.1038/S41467-023-44137-7",
                "note": null,
                "pmid": "38167262",
                "type": [],
                "pmcid": "PMC10762175",
                "version": null,
                "metadata": null
            }
        ],
        "additionDate": "2026-01-14T07:17:23.617848Z",
        "collectionID": [],
        "elixir_badge": 0,
        "accessibility": null,
        "biotoolsCURIE": "biotools:nanoranger",
        "documentation": [],
        "editPermission": {
            "type": "private",
            "authors": []
        },
        "elixirPlatform": [],
        "confidence_flag": null,
        "elixirCommunity": [],
        "homepage_status": 0,
        "operatingSystem": []
    },
    "harvested_at": "2026-10-12T03:21:38.048093Z",
    "pipeline_tag": "bioschemas@0.1.0",
    "date_created": "2026-01-14T07:17:23.617848Z",
    "date_published": null,
    "date_modified": "2026-01-14T07:17:23.620981Z"
}
"""


def main():
    description = asyncio.run(
        enrich_tool_metadata(
            raw_metadata=raw_metadata,
            endpoint_url=LLM_API,
            api_key=EGI_LLM_API_KEY,
        )
    )
    print(description)


if __name__ == "__main__":
    main()
