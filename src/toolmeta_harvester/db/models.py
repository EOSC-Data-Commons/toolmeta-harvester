from sqlalchemy import (
    Column,
    Integer,
    DateTime,
    Identity,
    String,
    func,
)

from toolmeta_models import Base
import string
import secrets


def generate_alphanum_id(length=9):
    chars = string.ascii_lowercase + string.digits
    return "".join(secrets.choice(chars) for _ in range(length))


def generate_tool_id():
    return f"edc:tool:{generate_alphanum_id()}"


class ToolHarvest(Base):
    __tablename__ = "_tool_harvest"

    id = Column(
        Integer, Identity(start=1), autoincrement=True, primary_key=True
    )  # logical repository id
    url = Column(String, nullable=False, index=True)
    # pending, error, processing, completed
    status = Column(String, nullable=False)
    # HTTP error code if applicable
    eror_code = Column(String)
    # usegalaxy.org, workflowhub.eu, ...
    source_type = Column(String, nullable=False)
    # galaxy_workflow, galaxy_tool, cwl_tool, nextflow_pipeline, ...
    artifact_type = Column(String, nullable=False)
    # id of the stored artifact in the corresponding table
    stored_id = Column(String)
    # name of the corresponding table where the artifact is stored
    stored_table = Column(String)
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
