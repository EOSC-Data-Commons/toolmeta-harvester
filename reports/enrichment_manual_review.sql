-- Review the newest enrichment experiment across source metadata, LLM output,
-- per-stage model/prompt provenance, validation, and the linked embedding.
-- To inspect a particular experiment, replace latest_run with:
--   SELECT 'your-run-uuid'::uuid AS id
WITH latest_run AS (
    SELECT id
    FROM public.tool_enrichment_runs
    WHERE name NOT LIKE 'legacy-%'
    ORDER BY started_at DESC
    LIMIT 1
)
SELECT
    r.id AS enrichment_run_id,
    r.name AS experiment_name,
    r.status AS run_status,
    r.started_at AS run_started_at,
    r.finished_at AS run_finished_at,
    r.requested_extraction_model,
    e.extraction_model AS actual_extraction_model,
    r.extraction_prompt_version,
    r.requested_generation_model,
    e.generation_model AS actual_generation_model,
    r.generation_prompt_version,
    r.requested_validation_model,
    e.validation_model AS actual_validation_model,
    r.validation_prompt_version,
    t.id AS tool_id,
    t.metadata_format AS source_format,
    t.source_identifier,
    t.source_url,
    t.title,
    t.description AS source_description,
    t.raw_description AS source_raw_description,
    t.keywords AS source_keywords,
    t.types AS source_types,
    t.inputs AS source_inputs,
    t.outputs AS source_outputs,
    t.consumes_data AS source_consumes_data,
    t.produces_data AS source_produces_data,
    t.raw_metadata AS source_raw_metadata,
    e.status AS enrichment_status,
    e.input_hash,
    e.input_description,
    e.output_description,
    e.semantic_metadata AS all_extracted_enriched_attributes,
    e.semantic_metadata -> 'supported_tasks' AS supported_tasks,
    e.semantic_metadata -> 'methods_and_techniques' AS methods_and_techniques,
    e.semantic_metadata -> 'scientific_domains' AS scientific_domains,
    e.enriched_description,
    e.validation -> 'accuracy_score' AS accuracy_score,
    e.validation -> 'completeness_score' AS completeness_score,
    e.validation -> 'input_quality_score' AS input_quality_score,
    e.validation -> 'output_quality_score' AS output_quality_score,
    e.validation -> 'enriched_description_score' AS enriched_description_score,
    e.validation -> 'semantic_usefulness_score' AS semantic_usefulness_score,
    e.validation -> 'hallucination_detected' AS hallucination_detected,
    e.validation -> 'issues' AS validation_issues,
    e.validation -> 'overall_assessment' AS overall_assessment,
    e.error AS enrichment_error,
    e.failed_stage,
    em.embedding_model,
    em.embedding_type,
    em.text AS embedded_text,
    vector_dims(em.vector) AS embedding_dimensions,
    em.created_at AS embedding_created_at
FROM latest_run lr
JOIN public.tool_enrichment_runs r ON r.id = lr.id
JOIN public.tool_enrichments e ON e.run_id = r.id
JOIN public.tool_metadata t ON t.id = e.tool_id
LEFT JOIN public.tool_embeddings em
    ON em.enrichment_id = e.id
   AND em.embedding_type = 'enriched_description'
ORDER BY t.metadata_format, t.title, t.id;
