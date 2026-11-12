from sqlalchemy import URL, create_engine
from toolmeta_harvester.config import load_db_config
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


db = load_db_config()

engine = create_engine(
    URL.create(
        drivername="postgresql+psycopg",
        username=db.user,
        password=db.password,
        host=db.host,
        port=db.port,
        database=db.name,
    ),
    echo=False,
    future=True,
)
