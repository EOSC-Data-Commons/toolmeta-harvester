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
    return "".join(secrets.choice(chars) for _ in range(length))


def generate_tool_id():
    return f"edc:tool:{generate_alphanum_id()}"


Base = declarative_base()


class ArtifactHarvest(Base):
    __tablename__ = "artifact_harvests"

    id = Column(
        Integer, Identity(start=1), autoincrement=True, primary_key=True
    )  # logical repository id
    url = Column(Text, nullable=False, index=True)
    # pending, error, processing, completed
    status = Column(Text, nullable=False)
    # HTTP error code if applicable
    eror_code = Column(Text)
    # usegalaxy.org, workflowhub.eu, ...
    source_type = Column(Text, nullable=False)
    # galaxy_workflow, galaxy_tool, cwl_tool, nextflow_pipeline, ...
    artifact_type = Column(Text, nullable=False)
    # id of the stored artifact in the corresponding table
    stored_id = Column(Text, nullable=False)
    # name of the corresponding table where the artifact is stored
    stored_table = Column(Text, nullable=False)
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


class GalaxyWorkflow(Base):
    __tablename__ = "galaxy_workflows"

    id = Column(
        String, primary_key=True, unique=True, nullable=False
    )  # logical workflow id
    name = Column(Text, nullable=False)
    description = Column(Text)
    url = Column(Text, nullable=False, index=True)
    version = Column(Text)
    input_toolshed_tools = Column(ARRAY(Text))
    output_toolshed_tools = Column(ARRAY(Text))
    toolshed_tools = Column(ARRAY(Text))
    tags = Column(ARRAY(Text))
    raw_ga = Column(LargeBinary, nullable=False)  # raw JSON
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


# class Repository(Base):
#     __tablename__ = "repositories"
#
#     id = Column(
#         Integer, Identity(start=1), autoincrement=True, primary_key=True
#     )  # logical repository id
#     url = Column(Text, nullable=False, index=True)  # repository URL
#     no_tools = Column(Integer)  # number of tools found
#     # active, archived, deleted, ...
#     status = Column(Text, nullable=False)
#     # HTTP error code if applicable
#     eror_code = Column(Text)
#
#     source_type = Column(Text, nullable=False)  # galaxy, cwl, nextflow, ...
#
#     created_at = Column(
#         DateTime(timezone=True),
#         server_default=func.now(),
#         nullable=False,
#     )
#
#     updated_at = Column(
#         DateTime(timezone=True),
#         server_default=func.now(),
#         onupdate=func.now(),
#         nullable=False,
#     )
#
#
class ShedTool(Base):
    __tablename__ = "shed_tools"

    id = Column(String, primary_key=True, unique=True, nullable=False)
    name = Column(Text, nullable=False)
    version = Column(Text)

    source_type = Column(Text, nullable=False)  # galaxy, cwl, nextflow, ...
    source_url = Column(Text)

    description = Column(Text)
    categories = Column(ARRAY(Text))
    owner = Column(Text)

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
        "ShedToolInput",
        back_populates="tool",
        cascade="all, delete-orphan",
    )

    outputs = relationship(
        "ShedToolOutput",
        back_populates="tool",
        cascade="all, delete-orphan",
    )
    __table_args__ = (
        UniqueConstraint(
            "name", "version", "source_type", name="uq_tool_name_version_source"
        ),
    )


class ToolInput(Base):
    __tablename__ = "shed_tool_inputs"

    id = Column(
        Integer, Identity(start=1), autoincrement=True, primary_key=True
    )  # logical output id

    tool_id = Column(String, ForeignKey("shed_tools.id", ondelete="CASCADE"))
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

    tool = relationship("ShedTool", back_populates="inputs")


class ShedToolOutput(Base):
    __tablename__ = "shed_tool_outputs"

    id = Column(
        Integer, Identity(start=1), autoincrement=True, primary_key=True
    )  # logical output id

    tool_id = Column(String, ForeignKey("shed_tools.id", ondelete="CASCADE"))
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

    tool = relationship("ShedTool", back_populates="outputs")
