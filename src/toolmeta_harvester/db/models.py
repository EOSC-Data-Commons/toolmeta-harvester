from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    Boolean,
    String,
    Text,
    Float,
    func,
    UniqueConstraint,
    Index,
    text,
    DDL,
    event,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from pgvector.sqlalchemy import Vector

from dataclasses import dataclass
from toolmeta_harvester.db.engine import Base

EMBEDDING_TYPES = [
    "description",
    "description_enriched_01",
    "description_enriched_02",
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

    # description, keywords, authors, metadata, ...
    embedding_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    embedding_model: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )

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
        UniqueConstraint(
            "tool_id",
            "embedding_type",
            "embedding_model",
            name="uq_tool_embedding",
        ),
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
                postgresql_where=text(
                    f"embedding_type = '{embedding_type}' "
                    f"AND embedding_model = '{EMBEDDING_MODEL}'"
                ),
            )
            for embedding_type in EMBEDDING_TYPES
        ),
    )


class HarvestSource(Base):
    __tablename__ = "harvest_source"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    url: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        unique=True,
    )

    schedule: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="true",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
