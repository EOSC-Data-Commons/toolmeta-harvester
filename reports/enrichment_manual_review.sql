-- Compare every sampled tool's source metadata and enriched attributes.
-- Set the experiment UUID below to the run being reviewed; the same query
-- presents both A (direct generation) and B (extraction + generation).
WITH selected_experiment AS (
    SELECT '23c03cf7-0c4f-425a-b44d-fb16755605f5'::uuid AS experiment_id
),
sample_results AS (
    SELECT e.*, t.metadata_format, t.title, t.source_url, t.description,
           t.raw_description, t.keywords, t.types, t.software_types,
           t.consumes_data, t.produces_data, t.inputs, t.outputs,
           t.raw_metadata
    FROM tool_enrichments AS e
    JOIN tool_metadata AS t ON t.id = e.tool_id
    JOIN selected_experiment AS x ON x.experiment_id = e.experiment_id
)
SELECT
    a.experiment_id,
    a.tool_id,
    a.metadata_format AS source,
    a.title,
    a.source_url,
    a.description AS source_description,
    a.raw_description AS source_raw_description,
    a.keywords AS source_keywords,
    a.types AS source_types,
    a.software_types AS source_software_types,
    a.consumes_data AS source_consumes_data,
    a.produces_data AS source_produces_data,
    a.inputs AS source_inputs,
    a.outputs AS source_outputs,
    a.raw_metadata AS source_raw_metadata,

    a.status AS status_a,
    a.extraction_used AS extraction_used_a,
    a.extraction_result AS extracted_attributes_a,
    a.enriched_description AS enriched_description_a,
    a.deterministic_validation AS deterministic_validation_a,
    a.validation_status AS validation_status_a,
    a.validation AS llm_validation_a,
    a.requested_extraction_model AS requested_extraction_model_a,
    a.extraction_model AS actual_extraction_model_a,
    a.requested_model AS requested_generation_model_a,
    a.model AS actual_generation_model_a,
    a.requested_validation_model AS requested_validation_model_a,
    a.validation_model AS actual_validation_model_a,
    a.extraction_prompt_version AS extraction_prompt_version_a,
    a.prompt_version AS generation_prompt_version_a,
    a.validation_prompt_version AS validation_prompt_version_a,
    a.extraction_request_count AS extraction_requests_a,
    a.generation_request_count AS generation_requests_a,
    a.validation_request_count AS validation_requests_a,
    a.extraction_elapsed_seconds AS extraction_seconds_a,
    a.generation_elapsed_seconds AS generation_seconds_a,
    a.validation_elapsed_seconds AS validation_seconds_a,
    ea.embedding_model AS requested_embedding_model_a,
    ea.actual_model AS actual_embedding_model_a,
    ea.embedding_type AS embedding_type_a,
    ea.vector <=> eb.vector AS embedding_cosine_distance_a_to_b,

    b.status AS status_b,
    b.extraction_used AS extraction_used_b,
    b.extraction_result AS extracted_attributes_b,
    b.enriched_description AS enriched_description_b,
    b.deterministic_validation AS deterministic_validation_b,
    b.validation_status AS validation_status_b,
    b.validation AS llm_validation_b,
    b.requested_extraction_model AS requested_extraction_model_b,
    b.extraction_model AS actual_extraction_model_b,
    b.requested_model AS requested_generation_model_b,
    b.model AS actual_generation_model_b,
    b.requested_validation_model AS requested_validation_model_b,
    b.validation_model AS actual_validation_model_b,
    b.extraction_prompt_version AS extraction_prompt_version_b,
    b.prompt_version AS generation_prompt_version_b,
    b.validation_prompt_version AS validation_prompt_version_b,
    b.extraction_request_count AS extraction_requests_b,
    b.generation_request_count AS generation_requests_b,
    b.validation_request_count AS validation_requests_b,
    b.extraction_elapsed_seconds AS extraction_seconds_b,
    b.generation_elapsed_seconds AS generation_seconds_b,
    b.validation_elapsed_seconds AS validation_seconds_b,
    eb.embedding_model AS requested_embedding_model_b,
    eb.actual_model AS actual_embedding_model_b,
    eb.embedding_type AS embedding_type_b,
    a.source_hash,
    a.extraction_input_hash AS extraction_request_hash_a,
    b.extraction_input_hash AS extraction_request_hash_b,
    a.input_hash AS generation_request_hash_a,
    b.input_hash AS generation_request_hash_b,
    a.error AS error_a,
    b.error AS error_b
FROM sample_results AS a
LEFT JOIN sample_results AS b
       ON b.experiment_id = a.experiment_id
      AND b.tool_id = a.tool_id
      AND b.variant = 'B'
LEFT JOIN tool_embeddings AS ea ON ea.enrichment_id = a.id
LEFT JOIN tool_embeddings AS eb ON eb.enrichment_id = b.id
WHERE a.variant = 'A'
ORDER BY a.metadata_format, a.title, a.tool_id;
