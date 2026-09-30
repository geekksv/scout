from sqlalchemy import event
from sqlmodel import Session, SQLModel, create_engine

from .config import DB_URL

IS_SQLITE = DB_URL.startswith("sqlite")

if IS_SQLITE:
    engine = create_engine(DB_URL, connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(conn, _record):
        cur = conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()
else:
    # Hosted Postgres: small pool, and recycle connections the free tier may drop.
    engine = create_engine(DB_URL, pool_size=5, max_overflow=5, pool_pre_ping=True, pool_recycle=300)


def init_db() -> None:
    from . import models  # noqa: F401  (register tables)

    SQLModel.metadata.create_all(engine)


def get_session():
    with Session(engine) as session:
        yield session
