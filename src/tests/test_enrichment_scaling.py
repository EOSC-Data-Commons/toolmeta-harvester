from uuid import uuid4

from toolmeta_harvester.enrichment.pipeline import select_enrichment_batches


def test_fifty_thousand_ids_map_to_bounded_batches_without_losing_records():
    ids = [str(uuid4()) for _ in range(50_000)]
    batches = select_enrichment_batches(
        tool_ids=ids,
        limit=None,
        full_catalog=False,
        batch_size=10,
    )
    assert len(batches) == 5_000
    assert all(1 <= len(batch) <= 10 for batch in batches)
    assert [value for batch in batches for value in batch] == ids
