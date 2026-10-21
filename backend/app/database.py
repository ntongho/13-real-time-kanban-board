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
  * postgres://...   -> normalized to postgresql://... (Render/Heroku style URLs)
  * postgresql://... -> used as-is (add ?sslmode=require for Neon/Supabase)
No credentials are ever hard-coded here; hosts set DATABASE_URL as an env var.
"""
from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import create_engine, event
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

    1. Misspelled `postgres://` scheme (still emitted by some hosts) is not
       understood by SQLAlchemy 2.x and must become `postgresql://`.
    2. A blank/whitespace env var falls back to local SQLite instead of
       creating an engine with an empty URL.
    """
    url = (raw or "").strip()
    if not url:
        return DEFAULT_DATABASE_URL
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
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


def init_db() -> None:
    """Create tables and seed the three MVP columns. Called on app startup."""
    from . import models  # noqa: F401  (registers tables on Base.metadata)

    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        seed_default_columns(db)
    finally:
        db.close()
