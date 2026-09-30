from sqlalchemy import event, inspect, text
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
    _add_missing_columns()


def _add_missing_columns() -> None:
    """create_all never alters existing tables; add columns introduced since a database
    was created, so upgrading keeps old runs readable. (Additive only, no type changes.)"""
    insp = inspect(engine)
    with engine.begin() as conn:
        for table in SQLModel.metadata.sorted_tables:
            if not insp.has_table(table.name):
                continue
            existing = {c["name"] for c in insp.get_columns(table.name)}
            for col in table.columns:
                if col.name in existing:
                    continue
                ddl_type = col.type.compile(dialect=engine.dialect)
                default = " DEFAULT ''" if ddl_type.upper() in ("TEXT", "VARCHAR") else ""
                conn.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN "{col.name}" {ddl_type}{default}'))


def get_session():
    with Session(engine) as session:
        yield session
