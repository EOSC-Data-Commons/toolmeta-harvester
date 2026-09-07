from sqlalchemy import create_engine
from toolmeta_harvester.config import load_db_config
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


db = load_db_config()

engine = create_engine(
    f"postgresql+psycopg://{db.user}:{db.password}@{db.host}/{db.name}",
    echo=False,
    future=True,
)
