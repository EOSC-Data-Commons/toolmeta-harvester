from toolmeta_harvester.db.engine import engine
from toolmeta_harvester.db.models import Base

def create_tables():
    """Create all tables in the database."""
    Base.metadata.create_all(engine)

if __name__ == "__main__":
    create_tables()
    print("All tables created successfully.")
