from pathlib import Path

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session

DB_PATH = Path(__file__).resolve().parents[3] / "data" / "pokedex.db"
DATABASE_URL = f"sqlite:///{DB_PATH}"


def get_engine(database_url: str = DATABASE_URL) -> Engine:
    engine = create_engine(database_url)

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


def get_session(engine: Engine | None = None) -> Session:
    return Session(engine or get_engine())
