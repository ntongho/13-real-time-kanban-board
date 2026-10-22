"""
Database engine, session, and seeding — owned by Member 2.

Public contract that Member 1 (routes), Member 4 (realtime) and Member 5
(wiring/deploy) import from this module:

    Base          -> declarative base for Member 2's models
    engine        -> SQLAlchemy engine
    SessionLocal  -> session factory
    get_db()      -> FastAPI dependency yielding a session
    init_db()     -> create tables + seed the three MVP columns (idempotent)

Configuration
-------------
`DATABASE_URL` selects the database.
  * unset            -> local SQLite file at backend/kanban.db
  * postgres://...   -> normalized to postgresql+psycopg://... (Render-style URLs)
  * postgresql://... -> normalized to the installed psycopg 3 driver (add ?sslmode=require for Neon/Supabase)
No credentials are ever hard-coded here; hosts set DATABASE_URL as an env var.
"""
from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import StaticPool

# backend/app/database.py -> parents[0] = app/, parents[1] = backend/
BACKEND_DIR = Path(__file__).resolve().parents[1]

# Anchor the default SQLite file next to the backend package instead of the
# current working directory. Without this, `uvicorn` started from the repo root
# and from backend/ would silently create two different kanban.db files.
DEFAULT_SQLITE_PATH = BACKEND_DIR / "kanban.db"
DEFAULT_DATABASE_URL = f"sqlite:///{DEFAULT_SQLITE_PATH}"


def normalize_database_url(raw: str | None) -> str:
    """Return a SQLAlchemy-usable URL, applying the two fixes hosts trip on.

    1. Convert common Postgres URL schemes to SQLAlchemy's psycopg 3 dialect,
       which is the driver installed by backend/requirements.txt.
    2. A blank/whitespace env var falls back to local SQLite instead of
       creating an engine with an empty URL.
    """
    url = (raw or "").strip()
    if not url:
        return DEFAULT_DATABASE_URL
    if url.startswith("postgres://"):
        url = "postgresql+psycopg://" + url[len("postgres://"):]
    elif url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


DATABASE_URL = normalize_database_url(os.getenv("DATABASE_URL"))
IS_SQLITE = DATABASE_URL.startswith("sqlite")


def _engine_kwargs(url: str) -> dict:
    kwargs: dict = {
        # Recycle dead connections instead of erroring after a hosted Postgres
        # instance goes to sleep and wakes up (free-tier behaviour).
        "pool_pre_ping": True,
    }
    if url.startswith("sqlite"):
        # FastAPI runs sync endpoints in a threadpool, so the connection is
        # used from a different thread than the one that opened it.
        kwargs["connect_args"] = {"check_same_thread": False}
        if ":memory:" in url:
            # Without StaticPool every connection would get its own empty
            # in-memory database and tables would appear to vanish.
            kwargs["poolclass"] = StaticPool
    return kwargs


engine = create_engine(DATABASE_URL, **_engine_kwargs(DATABASE_URL))


if IS_SQLITE:

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_connection, _connection_record):
        """SQLite ignores FOREIGN KEY constraints unless asked not to.

        Without this, a card could reference a column that does not exist and
        the API would happily persist corrupt data.
        """
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
        finally:
            cursor.close()


SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)

Base = declarative_base()

# The three MVP columns from the Team Build Guide. Order matters: it is the
# left-to-right board order.
DEFAULT_COLUMNS: tuple[tuple[str, str, int], ...] = (
    ("todo", "To Do", 0),
    ("doing", "In Progress", 1),
    ("done", "Done", 2),
)


def get_db():
    """FastAPI dependency: hand out a session, always close it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def seed_default_columns(db) -> int:
    """Insert any missing default column. Returns how many were created.

    Idempotent: safe to call on every startup and in tests.
    """
    from .models import BoardColumn  # local import avoids a circular import

    existing = {row[0] for row in db.query(BoardColumn.id).all()}
    created = 0
    for column_id, title, position in DEFAULT_COLUMNS:
        if column_id not in existing:
            db.add(BoardColumn(id=column_id, title=title, position=position))
            created += 1
    if created:
        db.commit()
    return created


def migrate_activity_delete_action(target_engine=engine) -> bool:
    """Allow the `deleted` audit action on databases created before card deletion.

    SQLAlchemy create_all() does not alter existing CHECK constraints. Rebuild
    the SQLite activity table while preserving rows, or replace the named
    PostgreSQL constraint. Returns True only when a migration was applied.
    """
    from .models import Activity

    if target_engine.dialect.name == "sqlite":
        with target_engine.begin() as connection:
            ddl = connection.execute(text(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name='activities'"
            )).scalar()
            if not ddl or "'deleted'" in ddl.lower():
                return False
            connection.exec_driver_sql("ALTER TABLE activities RENAME TO activities_legacy")
            connection.exec_driver_sql("DROP INDEX IF EXISTS ix_activities_created_at")
            Activity.__table__.create(bind=connection)
            columns = "id, action, card_id, card_title, from_column, to_column, message, created_at"
            connection.exec_driver_sql(
                f"INSERT INTO activities ({columns}) SELECT {columns} FROM activities_legacy"
            )
            connection.exec_driver_sql("DROP TABLE activities_legacy")
        return True

    if target_engine.dialect.name == "postgresql":
        with target_engine.begin() as connection:
            connection.exec_driver_sql(
                "ALTER TABLE activities DROP CONSTRAINT IF EXISTS ck_activities_action_valid"
            )
            connection.exec_driver_sql(
                "ALTER TABLE activities ADD CONSTRAINT ck_activities_action_valid "
                "CHECK (action IN ('created', 'moved', 'deleted'))"
            )
        return True

    return False


def init_db() -> None:
    """Create tables, apply small schema compatibility migration, and seed columns."""
    from . import models  # noqa: F401  (registers tables on Base.metadata)

    Base.metadata.create_all(bind=engine)
    migrate_activity_delete_action(engine)

    db = SessionLocal()
    try:
        seed_default_columns(db)
    finally:
        db.close()
