from sqlalchemy import (
    Column,
    Text,
    Boolean,
    ForeignKey,
    DateTime,
    LargeBinary,
    func,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

class Tool(Base):
    __tablename__ = "tool"

    id = Column(Text, primary_key=True)           # logical tool id
    name = Column(Text, nullable=False)
    version = Column(Text)

    source_type = Column(Text, nullable=False)    # galaxy, cwl, nextflow, ...
    source_url = Column(Text)

    command = Column(Text)                         # extracted executable command

    raw = Column(LargeBinary, nullable=False)      # raw XML/YAML/JSON/etc.
    raw_format = Column(Text, nullable=False)      # xml, yaml, json, nf, ...

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    inputs = relationship(
        "ToolInput",
        back_populates="tool",
        cascade="all, delete-orphan",
    )

    outputs = relationship(
        "ToolOutput",
        back_populates="tool",
        cascade="all, delete-orphan",
    )

class ToolInput(Base):
    __tablename__ = "tool_input"

    tool_id = Column(
        Text,
        ForeignKey("tool.id", ondelete="CASCADE"),
        primary_key=True,
    )
    name = Column(Text, primary_key=True)
    type = Column(Text, nullable=True)
    format = Column(Text, nullable=True)
    is_optional = Column(Boolean, default=False)

    tool = relationship("Tool", back_populates="inputs")


class ToolOutput(Base):
    __tablename__ = "tool_output"

    tool_id = Column(
        Text,
        ForeignKey("tool.id", ondelete="CASCADE"),
        primary_key=True,
    )
    name = Column(Text, primary_key=True)
    type = Column(Text, nullable=True)
    format = Column(Text, nullable=False)

    tool = relationship("Tool", back_populates="outputs")

