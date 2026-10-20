from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from uuid import UUID

from toolmeta_harvester.enrichment.pipeline import (
    create_run,
    export_review_jsonl,
    run_embedding_stage,
    run_stage,
)

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
    parser.add_argument("--run-id", type=UUID)
    parser.add_argument(
        "--with-embeddings",
        action="store_true",
        help="Run the embedding stage after validation when --stage all is used.",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    if args.stage == "all":
        run_id = args.run_id or create_run(limit=SAMPLE_SIZE)
    else:
        if args.run_id is None and args.stage == "extraction":
            run_id = create_run(limit=SAMPLE_SIZE)
        elif args.run_id is None:
            parser.error("--run-id is required when running a single stage")
        else:
            run_id = args.run_id

    if args.stage == "embedding":
        processed = run_embedding_stage(run_id=run_id, limit=SAMPLE_SIZE)
        print(
            json.dumps(
                {"run_id": str(run_id), "stage": "embedding", "processed": processed}
            )
        )
        return

    stages = (
        ("extraction", "generation", "validation")
        if args.stage == "all"
        else (args.stage,)
    )
    results = [run_stage(stage, run_id=run_id, limit=SAMPLE_SIZE) for stage in stages]
    exported = export_review_jsonl(args.review_output, run_id=run_id, limit=SAMPLE_SIZE)
    embedding_count = (
        run_embedding_stage(run_id=run_id, limit=SAMPLE_SIZE)
        if args.stage == "all" and args.with_embeddings
        else None
    )
    print(
        json.dumps(
            {
                "results": results,
                "embedding_records": embedding_count,
                "run_id": str(run_id),
                "review_records": exported,
                "review_file": str(args.review_output),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
