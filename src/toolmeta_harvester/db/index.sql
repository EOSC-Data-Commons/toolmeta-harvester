-- Embedding index
CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_tool_embeddings_description_hnsw
ON tool_embeddings USING hnsw (vector vector_cosine_ops)
WHERE embedding_type = 'description'
  AND embedding_model = 'nomic-embed-text-v2-moe';

CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_tool_embeddings_description_enriched_01_hnsw
ON tool_embeddings USING hnsw (vector vector_cosine_ops)
WHERE embedding_type = 'description_enriched_01'
  AND embedding_model = 'nomic-embed-text-v2-moe';

CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_tool_embeddings_description_enriched_02_hnsw
ON tool_embeddings USING hnsw (vector vector_cosine_ops)
WHERE embedding_type = 'description_enriched_02'
  AND embedding_model = 'nomic-embed-text-v2-moe';

CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_tool_embeddings_authors_hnsw
ON tool_embeddings USING hnsw (vector vector_cosine_ops)
WHERE embedding_type = 'authors'
  AND embedding_model = 'nomic-embed-text-v2-moe';

CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_tool_embeddings_keywords_hnsw
ON tool_embeddings USING hnsw (vector vector_cosine_ops)
WHERE embedding_type = 'keywords'
  AND embedding_model = 'nomic-embed-text-v2-moe';

-- Tool metadata index
CREATE EXTENSION IF NOT EXISTS pg_textsearch;

CREATE INDEX ix_tool_metadata_title_bm25
ON tool_metadata
USING bm25 (title)
WITH (text_config = 'english');

CREATE INDEX ix_tool_metadata_description_bm25
ON tool_metadata
USING bm25 (description)
WITH (text_config = 'english');

-- CREATE INDEX CONCURRENTLY ix_tool_metadata_types_gin
-- ON tool_metadata
-- USING gin (types);


-- Incremental embedding / metadata updates
CREATE INDEX CONCURRENTLY IF NOT EXISTS
    ix_tool_metadata_date_modified
ON tool_metadata (date_modified);

-- Harvesting history and recent records
CREATE INDEX CONCURRENTLY IF NOT EXISTS
    ix_tool_metadata_harvested_at
ON tool_metadata (harvested_at);

-- Filtering by harvesting pipeline
CREATE INDEX CONCURRENTLY IF NOT EXISTS
    ix_tool_metadata_pipeline_tag
ON tool_metadata (pipeline_tag);

-- Keyword array membership
CREATE INDEX CONCURRENTLY IF NOT EXISTS
    ix_tool_metadata_keywords_gin
ON tool_metadata
USING gin (keywords);

CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE INDEX CONCURRENTLY IF NOT EXISTS
    ix_tool_metadata_title_trgm
ON tool_metadata
USING gin (title gin_trgm_ops);

-- add search_types field
ALTER TABLE tool_metadata
ADD COLUMN search_types text[] NOT NULL DEFAULT '{}';

CREATE INDEX CONCURRENTLY ix_tool_metadata_types_gin
ON tool_metadata
USING gin (search_types);

CREATE OR REPLACE FUNCTION update_tool_search_types()
RETURNS trigger AS $$
BEGIN
    SELECT COALESCE(
        ARRAY(
            SELECT DISTINCT lower(trim(value))
            FROM (
                SELECT unnest(NEW.types) AS value

                UNION ALL

                SELECT obj->>'name'
                FROM jsonb_array_elements(
                    NEW.programming_languages
                ) AS obj

                UNION ALL

                SELECT obj->>'name'
                FROM jsonb_array_elements(
                    NEW.runtime_platforms
                ) AS obj

                UNION ALL

                SELECT obj->>'name'
                FROM jsonb_array_elements(
                    NEW.software_types
                ) AS obj

                UNION ALL

                SELECT jsonb_array_elements_text(
                    CASE
                        WHEN jsonb_typeof(obj->'type') = 'array'
                        THEN obj->'type'
                        ELSE '[]'::jsonb
                    END
                )
                FROM jsonb_array_elements(
                    NEW.runtime_platforms
                ) AS obj

                UNION ALL

                SELECT jsonb_array_elements_text(
                    CASE
                        WHEN jsonb_typeof(obj->'type') = 'array'
                        THEN obj->'type'
                        ELSE '[]'::jsonb
                    END
                )
                FROM jsonb_array_elements(
                    NEW.software_types
                ) AS obj
            ) AS values
            WHERE value IS NOT NULL
              AND trim(value) <> ''
        ),
        '{}'
    )
    INTO NEW.search_types;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
