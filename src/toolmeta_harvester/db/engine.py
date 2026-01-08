from sqlalchemy import create_engine
from toolmeta_harvester.config import load_config

db = load_config()

engine = create_engine(
    f"postgresql+psycopg://{db.user}:{db.password}@{db.host}/{db.name}",
    echo=False,
    future=True,
)

