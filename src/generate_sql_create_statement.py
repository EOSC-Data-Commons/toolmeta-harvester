from sqlalchemy import text
from toolmeta_harvester.db.engine import engine
from toolmeta_harvester.db.models import (
    Base,
)
from toolmeta_models import ToolGeneric
from sqlalchemy.schema import CreateTable
from sqlalchemy.dialects import postgresql

print(
    CreateTable(ToolGeneric.__table__)
    .compile(dialect=postgresql.dialect())
)

# def main():
#     """Create all tables in the database."""
#     try:
#         with engine.connect() as conn:
#             result = conn.execute(text("SELECT 1"))
#             print("Connection OK:", result.scalar())
#         Base.metadata.create_all(engine)
#     except Exception as e:
#         print("Connection failed:", e)
#
# if __name__ == "__main__":
#     print("Creating tables in the database...")
#     main()


