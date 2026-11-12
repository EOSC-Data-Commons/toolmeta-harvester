from toolmeta_harvester.enrichment.report import _html_report, cosine_similarity
import pytest


def test_cosine_similarity_is_correct_and_handles_missing_vectors():
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == 0
    assert cosine_similarity([1.0, 1.0], [2.0, 2.0]) == pytest.approx(1)
    assert cosine_similarity(None, [1.0]) is None
    assert cosine_similarity([1.0], [1.0, 2.0]) is None
    assert cosine_similarity([0.0, 0.0], [1.0, 2.0]) is None


def test_html_report_renders_side_by_side_review_and_escapes_markup():
    scores = {
        "enriched_description_score": {"mean": 4.0, "median": 4.0},
    }
    metrics = {
        "experiment_id": "experiment-1",
        "sample_size": 1,
        "sample_sha256": "abc123",
        "variants": {
            "A": {"llm_evaluation": scores, "successes": 1},
            "B": {"llm_evaluation": scores, "successes": 1},
        },
        "comparison": {"embedding_cosine_similarity": {"mean": 0.97}},
        "actual_models_by_stage": {},
        "requested_models_by_stage": {},
        "prompt_versions_by_stage": {},
        "airflow_runs": {},
        "raw_metadata_audit": {},
    }
    rows = [
        {
            "tool_id": "tool-1",
            "title": "Tool <One>",
            "source": "codemeta",
            "source_metadata": {"description": "Source description"},
            "A": {"enriched_description": "Direct description"},
            "B": {
                "enriched_description": "Extracted description",
                "extraction_result": {"supported_tasks": ["analysis"]},
            },
        }
    ]

    document = _html_report(metrics, rows)

    assert "Tool metadata enrichment A/B experiment" in document
    assert "Automatic metrics" in document
    assert "LLM-as-judge" in document
    assert "Human judgement" in document
    assert "Direct description" in document
    assert "Extracted description" in document
    assert "Tool \\u003cOne>" in document
