from __future__ import annotations

import argparse
import json
from pathlib import Path
from uuid import UUID

from toolmeta_harvester.enrichment.report import generate_experiment_artifacts


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate reports from persisted A/B ToolDB results."
    )
    parser.add_argument("--experiment-id", type=UUID, required=True)
    parser.add_argument("--sample-path", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--airflow-metrics", type=Path)
    args = parser.parse_args()
    result = generate_experiment_artifacts(
        experiment_id=args.experiment_id,
        sample_path=args.sample_path,
        output_dir=args.output_dir,
        airflow_metrics_path=args.airflow_metrics,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
