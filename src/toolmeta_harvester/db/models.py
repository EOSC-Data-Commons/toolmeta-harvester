from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Index,
    text as sql_text,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from toolmeta_harvester.db.engine import Base

EMBEDDING_TYPES = [
    "description",
    "enriched_description",
    "authors",
    "keywords",
]

EMBEDDING_MODEL = "nomic-embed-text-v2-moe"


@dataclass(frozen=True)
class HarvestResult:
    pipeline_tag: str
    record_ids: list[str]
    failed_record_ids: list[str]

    @property
    def harvested_count(self) -> int:
        return len(self.record_ids)

    @property
    def failed_count(self) -> int:
        return len(self.failed_record_ids)


class ToolMetadata(Base):
    __tablename__ = "tool_metadata"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    quality_score: Mapped[float | None] = mapped_column(
        Float,
    )

    # -------------------------------------------------------------
    # Provenance
    # -------------------------------------------------------------

    source_identifier: Mapped[str | None] = mapped_column(Text)

    source_url: Mapped[str | None] = mapped_column(Text)

    metadata_url: Mapped[str | None] = mapped_column(Text)

    # ro-crate, codemeta, bioschemas, schema.org, ...
    metadata_format: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    metadata_version: Mapped[str | None] = mapped_column(String(100))

    # -------------------------------------------------------------
    # CodeMeta / schema.org core
    # -------------------------------------------------------------

    title: Mapped[str | None] = mapped_column(Text)

    description: Mapped[str | None] = mapped_column(Text)

    raw_description: Mapped[str | None] = mapped_column(Text)

    version: Mapped[str | None] = mapped_column(Text)

    license: Mapped[str | None] = mapped_column(Text)

    identifiers: Mapped[list[str]] = mapped_column(
        ARRAY(Text),
        default=list,
        nullable=False,
    )

    url: Mapped[str | None] = mapped_column(Text)

    code_repository: Mapped[str | None] = mapped_column(Text)

    keywords: Mapped[list[str]] = mapped_column(
        ARRAY(Text),
        default=list,
        nullable=False,
    )

    authors: Mapped[list[dict]] = mapped_column(
        JSONB,
        default=list,
        nullable=False,
    )

    organizations: Mapped[list[dict]] = mapped_column(
        JSONB,
        default=list,
        nullable=False,
    )

    types: Mapped[list[str]] = mapped_column(
        ARRAY(Text),
        default=list,
        nullable=False,
    )

    programming_languages: Mapped[list[dict]] = mapped_column(
        JSONB,
        default=list,
        nullable=False,
    )

    runtime_platforms: Mapped[list[dict]] = mapped_column(
        JSONB,
        default=list,
        nullable=False,
    )

    software_requirements: Mapped[list[dict]] = mapped_column(
        JSONB,
        default=list,
        nullable=False,
    )

    # -------------------------------------------------------------
    # CodeMeta scientific extensions
    # -------------------------------------------------------------

    # software-types
    software_types: Mapped[list[dict]] = mapped_column(
        JSONB,
        default=list,
        nullable=False,
    )

    # software-iodata
    consumes_data: Mapped[list[dict]] = mapped_column(
        JSONB,
        default=list,
        nullable=False,
    )

    produces_data: Mapped[list[dict]] = mapped_column(
        JSONB,
        default=list,
        nullable=False,
    )

    # -------------------------------------------------------------
    # RO-Crate inputs/outputs
    # -------------------------------------------------------------

    inputs: Mapped[list[dict]] = mapped_column(
        JSONB,
        default=list,
        nullable=False,
    )

    outputs: Mapped[list[dict]] = mapped_column(
        JSONB,
        default=list,
        nullable=False,
    )

    # -------------------------------------------------------------
    # Derived fields
    # -------------------------------------------------------------
    search_types: Mapped[list[str]] = mapped_column(
        ARRAY(Text),
        nullable=False,
        server_default="{}",
        comment=(
            "Derived field: normalised, deduplicated type labels "
            "extracted from types, programming_languages, "
            "runtime_platforms and software_types. "
            "Maintained automatically by a database trigger."
        ),
        info={
            "derived": True,
            "internal": True,
            "indexed": True,
        },
    )

    # -------------------------------------------------------------
    # Source preservation
    # -------------------------------------------------------------

    raw_metadata: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
    )

    harvested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    pipeline_tag: Mapped[str | None] = mapped_column(String(100))

    # harvest_run: Mapped["ToolHarvestRun"] = relationship(back_populates="records")

    date_created: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    date_published: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    date_modified: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint(
            "source_url",
            "source_identifier",
            name="uq_tool_metadata_source",
        ),
        # Full-text search
        Index(
            "ix_tool_metadata_title_bm25",
            "title",
            postgresql_using="bm25",
            postgresql_with={"text_config": "english"},
        ),
        Index(
            "ix_tool_metadata_description_bm25",
            "description",
            postgresql_using="bm25",
            postgresql_with={"text_config": "english"},
        ),
        # Fuzzy / substring title search
        Index(
            "ix_tool_metadata_title_trgm",
            "title",
            postgresql_using="gin",
            postgresql_ops={"title": "gin_trgm_ops"},
        ),
        # Array membership searches
        # Index(
        #     "ix_tool_metadata_types_gin",
        #     "types",
        #     postgresql_using="gin",
        # ),
        Index(
            "ix_tool_metadata_search_types_gin",
            "search_types",
            postgresql_using="gin",
        ),
        Index(
            "ix_tool_metadata_keywords_gin",
            "keywords",
            postgresql_using="gin",
        ),
        # Incremental harvesting and embedding
        Index(
            "ix_tool_metadata_date_modified",
            "date_modified",
        ),
        Index(
            "ix_tool_metadata_harvested_at",
            "harvested_at",
        ),
        # Filter by harvesting pipeline
        Index(
            "ix_tool_metadata_pipeline_tag",
            "pipeline_tag",
        ),
    )


class ToolEnrichment(Base):
    """One generated description, optionally using an extraction result."""

    __tablename__ = "tool_enrichments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tool_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tool_metadata.id", ondelete="CASCADE"),
        nullable=False,
    )
    experiment_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    variant: Mapped[str] = mapped_column(String(1), nullable=False)
    extraction_used: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sql_text("false")
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending", server_default="pending"
    )
    extraction_result: Mapped[dict | None] = mapped_column(JSONB)
    enriched_description: Mapped[str | None] = mapped_column(Text)
    source_hash: Mapped[str | None] = mapped_column(String(64))
    extraction_input_hash: Mapped[str | None] = mapped_column(String(64))
    input_hash: Mapped[str | None] = mapped_column(String(64))
    requested_extraction_model: Mapped[str | None] = mapped_column(String(200))
    extraction_model: Mapped[str | None] = mapped_column(String(200))
    requested_model: Mapped[str | None] = mapped_column(String(200))
    model: Mapped[str | None] = mapped_column(String(200))
    requested_validation_model: Mapped[str | None] = mapped_column(String(200))
    validation_model: Mapped[str | None] = mapped_column(String(200))
    extraction_prompt_version: Mapped[str | None] = mapped_column(String(100))
    prompt_version: Mapped[str | None] = mapped_column(String(100))
    validation_prompt_version: Mapped[str | None] = mapped_column(String(100))
    deterministic_validation: Mapped[dict | None] = mapped_column(JSONB)
    validation: Mapped[dict | None] = mapped_column(JSONB)
    extraction_validation: Mapped[dict | None] = mapped_column(JSONB)
    validation_status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="pending"
    )
    extraction_request_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    generation_request_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    validation_request_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    extraction_elapsed_seconds: Mapped[float | None] = mapped_column(Float)
    generation_elapsed_seconds: Mapped[float | None] = mapped_column(Float)
    validation_elapsed_seconds: Mapped[float | None] = mapped_column(Float)
    error: Mapped[str | None] = mapped_column(Text)
    failed_stage: Mapped[str | None] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint(
            "tool_id", "experiment_id", "variant", name="uq_tool_enrichment_variant"
        ),
        CheckConstraint("variant IN ('A', 'B')", name="ck_tool_enrichment_variant"),
        CheckConstraint(
            "(variant = 'A' AND extraction_used = false) OR "
            "(variant = 'B' AND extraction_used = true)",
            name="ck_tool_enrichment_extraction_variant",
        ),
        Index("ix_tool_enrichments_experiment_variant", "experiment_id", "variant"),
        Index("ix_tool_enrichments_status", "status"),
    )


class ToolEmbedding(Base):
    """A single embedding derived from a tool metadata record."""

    __tablename__ = "tool_embeddings"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    tool_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tool_metadata.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    enrichment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tool_enrichments.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    # description, keywords, authors, metadata, ...
    embedding_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    embedding_model: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )

    actual_model: Mapped[str | None] = mapped_column(String(200))

    embedding_batch_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), index=True
    )

    request_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )

    elapsed_seconds: Mapped[float | None] = mapped_column(Float)

    # Exact canonical text that was sent to the embedding model
    text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    vector: Mapped[list[float]] = mapped_column(
        Vector(768),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        *(
            Index(
                f"ix_tool_embeddings_{embedding_type}_hnsw",
                "vector",
                postgresql_using="hnsw",
                postgresql_ops={
                    "vector": "vector_cosine_ops",
                },
                postgresql_with={
                    "m": 16,
                    "ef_construction": 64,
                },
                postgresql_where=sql_text(
                    f"embedding_type = '{embedding_type}' "
                    f"AND embedding_model = '{EMBEDDING_MODEL}'"
                ),
            )
            for embedding_type in EMBEDDING_TYPES
        ),
        Index(
            "uq_tool_embedding_source",
            "tool_id",
            "embedding_type",
            "embedding_model",
            unique=True,
            postgresql_where=sql_text("enrichment_id IS NULL"),
        ),
        Index(
            "uq_tool_enrichment_embedding",
            "enrichment_id",
            "embedding_type",
            "embedding_model",
            unique=True,
            postgresql_where=sql_text("enrichment_id IS NOT NULL"),
        ),
    )
