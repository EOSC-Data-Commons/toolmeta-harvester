from toolmeta_harvester.db.engine import Base, engine
from toolmeta_harvester.db import models  # Register model definitions
from toolmeta_harvester.db.triggers import ensure_tool_search_types_trigger


def initialize_db():
    Base.metadata.create_all(bind=engine)
    ensure_tool_search_types_trigger(engine)
