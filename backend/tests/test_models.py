"""
Model / database-level tests — owned by Member 2.

test_api.py proves behaviour through HTTP. These tests go one layer down and
prove the schema itself refuses bad data, so persistence stays trustworthy even
if a future route (or a bug) writes to the database directly.

They also cover the configuration decisions documented in database.py:
  * DATABASE_URL normalization (postgres:// -> postgresql://)
  * the SQLite file being anchored to backend/ rather than the CWD
  * foreign keys actually being enforced on SQLite
"""
from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError

from app import models
from app.database import (
    DEFAULT_COLUMNS,
    DEFAULT_DATABASE_URL,
    normalize_database_url,
    seed_default_columns,
)


# ---------------------------------------------------------------------------
# DATABASE_URL handling
# ---------------------------------------------------------------------------

def test_postgres_scheme_is_normalized():
    """Hosts (and older Heroku docs) emit postgres:// which SQLAlchemy rejects."""
    assert (
        normalize_database_url("postgres://user:pw@host:5432/db")
        == "postgresql://user:pw@host:5432/db"
    )


def test_postgresql_scheme_is_left_alone():
    url = "postgresql://user:pw@host:5432/db?sslmode=require"
    assert normalize_database_url(url) == url


@pytest.mark.parametrize("blank", [None, "", "   ", "\n"])
def test_blank_database_url_falls_back_to_local_sqlite(blank):
    assert normalize_database_url(blank) == DEFAULT_DATABASE_URL


def test_default_sqlite_file_is_anchored_next_to_the_backend_package():
    """Regression guard: the DB path must not depend on the working directory.

    An earlier version used "sqlite:///./kanban.db", which created a different
    database depending on whether uvicorn was launched from the repo root or
    from backend/, so data appeared to vanish between runs.
    """
    assert DEFAULT_DATABASE_URL.startswith("sqlite:///")
    assert DEFAULT_DATABASE_URL.endswith("/backend/kanban.db")


def test_sqlite_foreign_keys_are_enabled(database):
    """PRAGMA foreign_keys defaults to OFF on SQLite; database.py turns it on."""
    if not database.IS_SQLITE:
        pytest.skip("PRAGMA is SQLite-specific")

    with database.engine.connect() as connection:
        from sqlalchemy import text

        assert connection.execute(text("PRAGMA foreign_keys")).scalar() == 1


# ---------------------------------------------------------------------------
# Seeding
# ---------------------------------------------------------------------------

def test_seed_returns_zero_when_columns_already_exist(db_session):
    assert seed_default_columns(db_session) == 0


def test_seeded_columns_match_the_agreed_contract(db_session):
    rows = db_session.query(models.BoardColumn).order_by(models.BoardColumn.position).all()

    assert [(r.id, r.title, r.position) for r in rows] == list(DEFAULT_COLUMNS)
    assert [r[0] for r in DEFAULT_COLUMNS] == list(models.COLUMN_IDS)


# ---------------------------------------------------------------------------
# Constraints
# ---------------------------------------------------------------------------

def test_blank_title_is_rejected_by_the_database(db_session):
    """Defence in depth: validation lives in the API, but the schema agrees."""
    db_session.add(models.Card(title="   ", column_id="todo", position=0))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_card_cannot_reference_a_missing_column(db_session):
    db_session.add(models.Card(title="orphan", column_id="archive", position=0))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_negative_position_is_rejected(db_session):
    db_session.add(models.Card(title="negative", column_id="todo", position=-1))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_activity_action_must_be_created_or_moved(db_session):
    db_session.add(
        models.Activity(
            action="deleted",
            card_id="x",
            card_title="x",
            to_column="todo",
            message="bogus",
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_card_ids_are_unique_uuids(db_session):
    first = models.Card(title="one", column_id="todo", position=0)
    second = models.Card(title="two", column_id="todo", position=1)
    db_session.add_all([first, second])
    db_session.commit()

    assert first.id != second.id
    assert len(first.id) == 36


def test_card_timestamps_are_set_on_insert_and_bumped_on_update(db_session):
    card = models.Card(title="timed", column_id="todo", position=0)
    db_session.add(card)
    db_session.commit()

    created_at = card.created_at
    assert created_at is not None
    assert card.updated_at is not None

    card.position = 5
    db_session.commit()
    assert card.updated_at >= created_at


# ---------------------------------------------------------------------------
# Relationships
# ---------------------------------------------------------------------------

def test_deleting_a_column_removes_its_cards_via_the_orm(db_session):
    from app.models import BoardColumn, Card

    column = BoardColumn(id="temp", title="Temp", position=99)
    db_session.add(column)
    db_session.add(Card(title="will go", column_id="temp", position=0))
    db_session.commit()

    db_session.delete(column)
    db_session.commit()

    assert db_session.query(Card).filter(Card.column_id == "temp").count() == 0


def test_activity_rows_are_independent_of_cards(db_session):
    """Activity is an audit log: no FK, so history survives card deletion."""
    activity = models.Activity(
        action="created",
        card_id="ghost-card",
        card_title="Deleted task",
        to_column="todo",
        message="Created 'Deleted task' in To Do",
    )
    db_session.add(activity)
    db_session.commit()

    assert db_session.query(models.Activity).filter_by(card_id="ghost-card").count() == 1
