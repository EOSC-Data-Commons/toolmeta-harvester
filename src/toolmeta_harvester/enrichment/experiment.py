from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from toolmeta_harvester.enrichment.pipeline import export_review_jsonl, run_stage

SAMPLE_SIZE = 100
DEFAULT_REVIEW_PATH = Path(".experiment-output/tool_enrichment_100.jsonl")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the deterministic 100-record semantic enrichment experiment."
    )
    parser.add_argument(
        "--stage",
        choices=("all", "extraction", "generation", "validation", "embedding"),
        default="all",
    )
    parser.add_argument("--review-output", type=Path, default=DEFAULT_REVIEW_PATH)
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    if args.stage == "embedding":
        from toolmeta_harvester.enrichment.pipeline import run_embedding_stage

        print(
            json.dumps(
                {"stage": "embedding", "processed": run_embedding_stage(limit=100)}
            )
        )
        return

    stages = (
        ("extraction", "generation", "validation")
        if args.stage == "all"
        else (args.stage,)
    )
    results = [run_stage(stage, limit=SAMPLE_SIZE) for stage in stages]
    exported = export_review_jsonl(args.review_output, limit=SAMPLE_SIZE)
    print(
        json.dumps(
            {
                "results": results,
                "review_records": exported,
                "review_file": str(args.review_output),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
