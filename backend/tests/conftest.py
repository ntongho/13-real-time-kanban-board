"""
Shared pytest fixtures — owned by Member 2 (test infrastructure).

Why this file exists
--------------------
`app/database.py` resolves DATABASE_URL when it is first imported. So the
environment has to be pointed at a throwaway database *before* any test module
imports the app. conftest.py is imported first by pytest, which makes it the
only safe place to do it.

The production SQLite file (backend/kanban.db) is never touched: every test run
gets its own temporary database, which is what the Team Build Guide means by
"use a test database, not demo/production data".

Running the tests
-----------------
    cd backend
    pytest -v

Optionally run against a real Postgres (CI or local docker):

    TEST_DATABASE_URL="postgresql://user:pass@localhost:5432/kanban_test" pytest -v

WARNING: the suite drops and recreates all tables, so TEST_DATABASE_URL must
point at a disposable database.
"""
from __future__ import annotations

import os
import sys
import tempfile
import uuid
from pathlib import Path

import pytest

# --- 1. Make `app` importable no matter which directory pytest was launched from
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# --- 2. Point the app at a disposable database BEFORE app.database is imported
TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL", "").strip()
IS_TEMP_SQLITE = not TEST_DATABASE_URL

if IS_TEMP_SQLITE:
    _tmp_dir = Path(tempfile.mkdtemp(prefix="kanban-tests-"))
    TEST_DATABASE_URL = f"sqlite:///{_tmp_dir / 'test.db'}"

os.environ["DATABASE_URL"] = TEST_DATABASE_URL
# Keep CORS deterministic during tests.
os.environ.setdefault("FRONTEND_ORIGINS", "http://localhost:5173")


@pytest.fixture(scope="session")
def app_module():
    """Import the FastAPI app once the test database env var is in place.

    The HTTP contract tests need Member 1's `routes.py` / `schemas.py`, which
    live on the `feat/api` branch, plus the `main.py` app wiring. On a branch
    where those files do not exist yet (e.g. bare `production`), skip with an
    explicit reason instead of erroring — the schema tests still run, and the
    skip message tells the reviewer exactly what to merge.
    """
    try:
        from app.main import app
    except ModuleNotFoundError as exc:
        pytest.skip(
            f"API layer not available ({exc}). Merge Member 1's feat/api branch "
            "(routes.py, schemas.py) and the app wiring in main.py to run the "
            "HTTP contract tests. The model tests in test_models.py run without it."
        )

    return app


@pytest.fixture()
def database():
    """The app's database module, bound to the test database."""
    from app import database as db_module

    return db_module


@pytest.fixture(autouse=True)
def fresh_schema(database):
    """Give every test an empty schema plus the three seeded columns.

    Autouse so a test can never inherit rows leaked by a previous one.
    """
    from app import models  # noqa: F401  (register tables on Base.metadata)

    database.Base.metadata.drop_all(bind=database.engine)
    database.Base.metadata.create_all(bind=database.engine)
    database.init_db()
    yield
    database.Base.metadata.drop_all(bind=database.engine)


@pytest.fixture()
def db_session(database):
    """A direct session for assertions that bypass the HTTP layer."""
    session = database.SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client(app_module):
    """TestClient with startup/shutdown events executed (so init_db runs)."""
    from fastapi.testclient import TestClient

    with TestClient(app_module) as test_client:
        yield test_client


@pytest.fixture()
def create_card(client):
    """Helper: POST a card and return the parsed response body."""

    def _create(title: str = "Sample task", description: str = "", column_id: str = "todo"):
        response = client.post(
            "/api/boards/demo/cards",
            json={"title": title, "description": description, "column_id": column_id},
        )
        assert response.status_code == 201, response.text
        return response.json()

    return _create


@pytest.fixture()
def board_columns(client):
    """Helper: {(column_id): [card titles in order]} for compact assertions."""

    def _snapshot() -> dict[str, list[str]]:
        board = client.get("/api/boards/demo").json()
        return {col["id"]: [card["title"] for card in col["cards"]] for col in board["columns"]}

    return _snapshot


@pytest.fixture()
def unique_title() -> str:
    """A title that cannot collide with seeded or leftover data."""
    return f"task-{uuid.uuid4().hex[:8]}"
