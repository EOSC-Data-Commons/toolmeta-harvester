# from sqlalchemy import (
#     Column,
#     Integer,
#     DateTime,
#     Identity,
#     String,
#     func,
# )
#
# from toolmeta_models import Base
# import string
# import secrets
#
#
# def generate_alphanum_id(length=9):
#     chars = string.ascii_lowercase + string.digits
#     return "".join(secrets.choice(chars) for _ in range(length))
#
#
# def generate_tool_id():
#     return f"edc:tool:{generate_alphanum_id()}"

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    Float,
    func,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class ToolHarvestRun(Base):
    __tablename__ = "tool_harvest_run"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # workflowhub, github, zenodo, ...
    source: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    source_url: Mapped[str | None] = mapped_column(Text)

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    status: Mapped[str] = mapped_column(
        String(50),
        default="running",
        nullable=False,
    )

    harvested_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    failed_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    records: Mapped[list["ToolMetadata"]] = relationship(back_populates="harvest_run")


class ToolMetadata(Base):
    __tablename__ = "tool_metadata"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    harvest_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "tool_harvest_run.id",
            ondelete="CASCADE",
        ),
        nullable=False,
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

    harvest_run: Mapped["ToolHarvestRun"] = relationship(back_populates="records")

    date_created: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    date_published: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    date_modified: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint(
            "source_url",
            "source_identifier",
            "version",
            name="uq_tool_metadata_source_url_identifier_version",
        ),
    )


# class ToolHarvest(Base):
#     __tablename__ = "_tool_harvest"
#
#     id = Column(
#         Integer, Identity(start=1), autoincrement=True, primary_key=True
#     )  # logical repository id
#     url = Column(String, nullable=False, index=True)
#     # pending, error, processing, completed
#     status = Column(String, nullable=False)
#     # HTTP error code if applicable
#     eror_code = Column(String)
#     # usegalaxy.org, workflowhub.eu, ...
#     source_type = Column(String, nullable=False)
#     # galaxy_workflow, galaxy_tool, cwl_tool, nextflow_pipeline, ...
#     artifact_type = Column(String, nullable=False)
#     # id of the stored artifact in the corresponding table
#     stored_id = Column(String)
#     # name of the corresponding table where the artifact is stored
#     stored_table = Column(String)
#     created_at = Column(
#         DateTime(timezone=True),
#         server_default=func.now(),
#         nullable=False,
#     )
#     updated_at = Column(
#         DateTime(timezone=True),
#         server_default=func.now(),
#         onupdate=func.now(),
#         nullable=False,
#     )
