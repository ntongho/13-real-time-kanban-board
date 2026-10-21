# Backend tests

Owned by **Member 2 (data model and persistence tests)**.

| File | Covers |
| --- | --- |
| `conftest.py` | Disposable test database, `client`, `db_session`, `create_card`, `board_columns` fixtures |
| `test_api.py` | HTTP contract + persistence + validation edge cases |
| `test_models.py` | Schema constraints, `DATABASE_URL` handling, relationships |

`test_realtime.py` (Member 4) and any route-specific tests Member 1 adds live
in this directory too and can reuse the fixtures below.

## Run them

```bash
cd backend
pip install -r requirements-dev.txt
pytest              # or: pytest -v
```

Expected: `50 passed`.

The suite never touches `backend/kanban.db`. `conftest.py` redirects
`DATABASE_URL` to a fresh temporary database before the app is imported, and
every test gets an empty schema plus the three seeded columns.

## Run against PostgreSQL

```bash
TEST_DATABASE_URL="postgresql://user:pass@localhost:5432/kanban_test" pytest
```

The suite **drops and recreates all tables**, so this must be a disposable
database. This is how to verify the sprint's "hosted DB URL configuration"
acceptance item before deploying.

## Fixtures available to other members

```python
def test_something(client, create_card, board_columns):
    card = create_card(title="A task", column_id="todo")   # returns card JSON
    assert board_columns() == {"todo": ["A task"], "doing": [], "done": []}
```

- `client` — `TestClient` with startup/shutdown run (so seeding happens)
- `db_session` — direct SQLAlchemy session for asserting the DB, not just the response
- `create_card(title=..., description=..., column_id=...)` — asserts 201, returns the body
- `board_columns()` — `{column_id: [card titles in order]}`
- `database` — the `app.database` module bound to the test engine
- `fresh_schema` — autouse; do not request it manually

## What the suite deliberately verifies

- Created and moved cards are present in the database **and** survive a fresh
  app instance (`engine.dispose()` + new `TestClient`), which is the
  "persists after reload" acceptance criterion.
- Blank titles (`""`, `"   "`, `"\n\t "`) are rejected with
  `{"detail": "Card title is required"}` and write **no** card and **no**
  activity row.
- Missing card → 404, invalid column → 422, negative position → 422, and a
  rejected move leaves the row untouched.
- Positions stay contiguous `0..n-1` after cross-column moves, same-column
  reorders, and out-of-range positions (clamped, not crashed).
- Activity rows are ordered newest-first and have microsecond-precision
  timestamps. SQLite's `CURRENT_TIMESTAMP` only has second resolution, which
  made ordering non-deterministic; `models.Activity.created_at` sets the value
  in Python instead.
- The schema refuses bad data independently of the API: blank title,
  unknown `column_id`, negative position, and invalid activity `action` all
  raise `IntegrityError`.
