from sqlalchemy import (
    Column,
    Text,
    Integer,
    Boolean,
    ForeignKey,
    DateTime,
    LargeBinary,
    Identity,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.dialects.postgresql import ARRAY
import string
import secrets

def generate_alphanum_id(length=9):
    chars = string.ascii_lowercase + string.digits
    return ''.join(secrets.choice(chars) for _ in range(length))

def generate_tool_id():
    return f"edc:tool:{generate_alphanum_id()}"



Base = declarative_base()

class Repository(Base):
    __tablename__ = "repositories"

    id = Column(Integer,
                Identity(start=1),
                autoincrement=True,
                primary_key=True)           # logical repository id
    url = Column(Text, nullable=False, index=True)  # repository URL
    no_tools = Column(Integer)                  # number of tools found
    status = Column(Text, nullable=False)        # active, archived, deleted, ...
    eror_code = Column(Text)                      # HTTP error code if applicable

    source_type = Column(Text, nullable=False)    # galaxy, cwl, nextflow, ...

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

class Tool(Base):
    __tablename__ = "tools"

    id = Column(String, primary_key=True, default=generate_tool_id, unique=True, nullable=False)           # logical tool id
    name = Column(Text, nullable=False)
    version = Column(Text)

    source_type = Column(Text, nullable=False)    # galaxy, cwl, nextflow, ...
    source_url = Column(Text)

    command = Column(LargeBinary)                         # extracted executable command

    raw = Column(LargeBinary, nullable=False)      # raw XML/YAML/JSON/etc.
    raw_format = Column(Text, nullable=False)      # xml, yaml, json, nf, ...

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
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
    __table_args__ = (
        UniqueConstraint('name', 'version', 'source_type', name='uq_tool_name_version_source'),
    )

class ToolInput(Base):
    __tablename__ = "tool_inputs"
    
    id = Column(Integer,
                Identity(start=1),
                autoincrement=True,
                primary_key=True)           # logical output id

    tool_id = Column(
        String,
        ForeignKey("tools.id", ondelete="CASCADE")
    )
    name = Column(Text, nullable=True)
    type = Column(Text, nullable=True)
    # format = Column(Text, nullable=True)
    format = Column(ARRAY(Text), nullable=True)
    label = Column(Text, nullable=True)
    is_optional = Column(Boolean, default=False)
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    tool = relationship("Tool", back_populates="inputs")
    


class ToolOutput(Base):
    __tablename__ = "tool_outputs"

    id = Column(Integer,
                Identity(start=1),
                autoincrement=True,
                primary_key=True)           # logical output id

    tool_id = Column(
        String,
        ForeignKey("tools.id", ondelete="CASCADE")
    )
    name = Column(Text, nullable=True)
    type = Column(Text, nullable=True)
    # format = Column(Text, nullable=False)
    format = Column(ARRAY(Text), nullable=True)
    label = Column(Text, nullable=True)
    
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


    tool = relationship("Tool", back_populates="outputs")

