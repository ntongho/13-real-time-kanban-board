"""
API contract & persistence tests — owned by Member 2.

These tests treat the HTTP API as the contract from the Team Build Guide and
verify the things this role is accountable for:

  * the app starts with exactly the three MVP columns
  * created and moved cards actually reach the database and survive a reload
  * validation rejects blank titles, bad columns, and unknown cards
  * positions stay contiguous so the board renders in a stable order
  * activity rows are written for successful mutations, newest first

They exercise Member 1's routes and Member 2's models together, which is the
integration point the guide calls out for this role. If Member 1 changes a
route's behaviour deliberately, update the matching test in the same PR.
"""
from __future__ import annotations

import uuid

import pytest

MVP_COLUMNS = {"todo": "To Do", "doing": "In Progress", "done": "Done"}
CARD_KEYS = {"id", "title", "description", "column_id", "position"}


# ---------------------------------------------------------------------------
# Startup & seeding
# ---------------------------------------------------------------------------

def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_startup_seeds_the_three_mvp_columns(client):
    board = client.get("/api/boards/demo").json()

    assert [(col["id"], col["title"]) for col in board["columns"]] == list(MVP_COLUMNS.items())
    # Board order is driven by BoardColumn.position, so assert it explicitly.
    assert [col["id"] for col in board["columns"]] == ["todo", "doing", "done"]
    assert all(col["cards"] == [] for col in board["columns"])


def test_init_db_is_idempotent(client, database):
    """Restarting the app must not duplicate the seeded columns."""
    database.init_db()
    database.init_db()

    board = client.get("/api/boards/demo").json()
    assert len(board["columns"]) == 3
    assert [col["id"] for col in board["columns"]] == ["todo", "doing", "done"]


def test_seed_restores_a_missing_column(client, db_session):
    """If a column row is lost, the next startup puts it back."""
    from app.models import BoardColumn

    db_session.query(BoardColumn).filter(BoardColumn.id == "done").delete()
    db_session.commit()

    from app.database import seed_default_columns

    assert seed_default_columns(db_session) == 1

    board = client.get("/api/boards/demo").json()
    assert [col["id"] for col in board["columns"]] == ["todo", "doing", "done"]


# ---------------------------------------------------------------------------
# Card shape contract
# ---------------------------------------------------------------------------

def test_created_card_matches_the_agreed_data_shape(create_card):
    card = create_card(title="Prepare demo slides", description="Optional notes")

    assert set(card) == CARD_KEYS
    # The id must be a real UUID string, because the frontend and the
    # WebSocket payloads key off it.
    assert str(uuid.UUID(card["id"])) == card["id"]
    assert card["title"] == "Prepare demo slides"
    assert card["description"] == "Optional notes"
    assert card["column_id"] == "todo"
    assert card["position"] == 0


def test_description_defaults_to_empty_string(create_card):
    card = create_card(title="No notes")
    assert card["description"] == ""


def test_board_groups_cards_into_the_right_columns(client, create_card):
    create_card(title="alpha", column_id="todo")
    create_card(title="beta", column_id="doing")
    create_card(title="gamma", column_id="done")

    board = client.get("/api/boards/demo").json()
    by_id = {col["id"]: [c["title"] for c in col["cards"]] for col in board["columns"]}

    assert by_id == {"todo": ["alpha"], "doing": ["beta"], "done": ["gamma"]}


# ---------------------------------------------------------------------------
# Persistence: the core promise of this role
# ---------------------------------------------------------------------------

def test_created_card_is_written_to_the_database(create_card, db_session):
    """Assert the row exists in the DB, not just in the HTTP response."""
    from app.models import Card

    card = create_card(title="Persisted task", description="durable")
    row = db_session.query(Card).filter(Card.id == card["id"]).one()

    assert row.title == "Persisted task"
    assert row.description == "durable"
    assert row.column_id == "todo"
    assert row.position == 0


def test_created_card_survives_a_reload(app_module, client, create_card):
    """A brand-new app instance must still see the card (survives reload)."""
    from fastapi.testclient import TestClient

    card = create_card(title="Survives reload")

    from app.database import engine

    engine.dispose()  # drop pooled connections, forcing a fresh connect

    with TestClient(app_module) as second_client:
        board = second_client.get("/api/boards/demo").json()

    titles = [c["title"] for col in board["columns"] for c in col["cards"]]
    assert "Survives reload" in titles
    assert card["id"] in [c["id"] for col in board["columns"] for c in col["cards"]]


def test_moved_card_persists_its_new_column(app_module, client, create_card, db_session):
    from app.models import Card
    from fastapi.testclient import TestClient

    card = create_card(title="Move me")
    response = client.patch(
        f"/api/cards/{card['id']}/move", json={"column_id": "doing", "position": 0}
    )
    assert response.status_code == 200
    assert response.json()["column_id"] == "doing"

    db_session.expire_all()
    assert db_session.query(Card).filter(Card.id == card["id"]).one().column_id == "doing"

    with TestClient(app_module) as second_client:
        board = second_client.get("/api/boards/demo").json()
    by_id = {col["id"]: [c["title"] for c in col["cards"]] for col in board["columns"]}
    assert by_id["doing"] == ["Move me"]
    assert by_id["todo"] == []


def test_cards_append_to_the_end_of_a_column(create_card):
    first = create_card(title="first")
    second = create_card(title="second")
    third = create_card(title="third")

    assert [first["position"], second["position"], third["position"]] == [0, 1, 2]


def test_title_is_trimmed_before_saving(create_card, db_session):
    from app.models import Card

    card = create_card(title="   Padded title   ")
    assert card["title"] == "Padded title"

    db_session.expire_all()
    assert db_session.query(Card).filter(Card.id == card["id"]).one().title == "Padded title"


# ---------------------------------------------------------------------------
# Validation & edge cases (the guide's required failure paths)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("blank_title", ["", "   ", "\n\t "])
def test_blank_title_is_rejected(client, blank_title):
    response = client.post(
        "/api/boards/demo/cards", json={"title": blank_title, "column_id": "todo"}
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "Card title is required"


def test_blank_title_creates_no_card(client, board_columns):
    client.post("/api/boards/demo/cards", json={"title": "   ", "column_id": "todo"})
    assert board_columns() == {"todo": [], "doing": [], "done": []}


def test_blank_title_creates_no_activity(client):
    client.post("/api/boards/demo/cards", json={"title": "   ", "column_id": "todo"})
    assert client.get("/api/boards/demo/activity").json() == []


def test_missing_title_is_rejected(client):
    response = client.post("/api/boards/demo/cards", json={"column_id": "todo"})
    assert response.status_code == 422
    assert "detail" in response.json()


def test_create_with_invalid_column_is_rejected(client, board_columns):
    response = client.post(
        "/api/boards/demo/cards", json={"title": "orphan", "column_id": "archive"}
    )

    assert response.status_code == 422
    assert "Invalid column_id" in response.json()["detail"]
    assert board_columns() == {"todo": [], "doing": [], "done": []}


def test_move_missing_card_returns_404(client):
    response = client.patch(
        f"/api/cards/{uuid.uuid4()}/move", json={"column_id": "doing", "position": 0}
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Card not found"


def test_move_to_invalid_column_is_rejected(client, create_card):
    card = create_card(title="stay put")
    response = client.patch(
        f"/api/cards/{card['id']}/move", json={"column_id": "archive", "position": 0}
    )

    assert response.status_code == 422
    assert "Invalid column_id" in response.json()["detail"]


def test_move_to_negative_position_is_rejected(client, create_card):
    card = create_card(title="negative")
    response = client.patch(
        f"/api/cards/{card['id']}/move", json={"column_id": "doing", "position": -1}
    )

    assert response.status_code == 422


def test_rejected_move_leaves_the_card_untouched(client, create_card, db_session):
    from app.models import Card

    card = create_card(title="unchanged")
    client.patch(
        f"/api/cards/{card['id']}/move", json={"column_id": "archive", "position": 0}
    )

    db_session.expire_all()
    row = db_session.query(Card).filter(Card.id == card["id"]).one()
    assert row.column_id == "todo"
    assert row.position == 0


# ---------------------------------------------------------------------------
# Ordering: positions must stay contiguous so the board renders predictably
# ---------------------------------------------------------------------------

def test_move_between_columns_keeps_positions_contiguous(client, create_card, board_columns):
    create_card(title="a")
    moving = create_card(title="b")
    create_card(title="c")

    client.patch(f"/api/cards/{moving['id']}/move", json={"column_id": "doing", "position": 0})

    assert board_columns() == {"todo": ["a", "c"], "doing": ["b"], "done": []}

    board = client.get("/api/boards/demo").json()
    for column in board["columns"]:
        positions = [card["position"] for card in column["cards"]]
        assert positions == list(range(len(positions))), f"{column['id']} has gaps: {positions}"


def test_reorder_within_a_column(client, create_card, board_columns):
    create_card(title="a")
    create_card(title="b")
    create_card(title="c")
    last = create_card(title="d")

    # Move the last card to the top of the same column.
    client.patch(f"/api/cards/{last['id']}/move", json={"column_id": "todo", "position": 0})

    assert board_columns()["todo"] == ["d", "a", "b", "c"]


def test_reorder_downward_within_a_column(client, create_card, board_columns):
    first = create_card(title="a")
    create_card(title="b")
    create_card(title="c")
    create_card(title="d")

    client.patch(f"/api/cards/{first['id']}/move", json={"column_id": "todo", "position": 2})

    assert board_columns()["todo"] == ["b", "c", "a", "d"]


def test_position_beyond_column_end_is_clamped(client, create_card, board_columns):
    """A stale UI sending position=999 must land at the end, not break order."""
    create_card(title="a")
    create_card(title="b")
    moving = create_card(title="c")

    response = client.patch(
        f"/api/cards/{moving['id']}/move", json={"column_id": "done", "position": 999}
    )

    assert response.status_code == 200
    assert board_columns()["done"] == ["c"]


def test_moving_into_a_populated_column_inserts_at_the_requested_index(
    client, create_card, board_columns
):
    create_card(title="d1", column_id="doing")
    create_card(title="d2", column_id="doing")
    incoming = create_card(title="incoming", column_id="todo")

    client.patch(
        f"/api/cards/{incoming['id']}/move", json={"column_id": "doing", "position": 1}
    )

    assert board_columns()["doing"] == ["d1", "incoming", "d2"]


# ---------------------------------------------------------------------------
# Activity history
# ---------------------------------------------------------------------------

def test_create_and_move_write_activity_newest_first(client, create_card):
    card = create_card(title="History task")
    client.patch(f"/api/cards/{card['id']}/move", json={"column_id": "doing", "position": 0})

    activity = client.get("/api/boards/demo/activity").json()

    assert len(activity) == 2
    # Newest first: the move happened last, so it is at index 0.
    assert activity[0]["action"] == "moved"
    assert activity[1]["action"] == "created"

    created, moved = activity[1], activity[0]
    assert created["card_id"] == card["id"]
    assert created["card_title"] == "History task"
    assert created["from_column"] is None
    assert created["to_column"] == "todo"
    assert moved["from_column"] == "todo"
    assert moved["to_column"] == "doing"


def test_activity_message_is_human_readable(client, create_card):
    card = create_card(title="Slides")
    client.patch(f"/api/cards/{card['id']}/move", json={"column_id": "done", "position": 0})

    messages = [row["message"] for row in client.get("/api/boards/demo/activity").json()]

    assert "Created 'Slides' in To Do" in messages
    assert "Moved 'Slides' from To Do to Done" in messages


def test_activity_timestamps_are_microsecond_precise(client, create_card):
    """Ties would make "newest first" non-deterministic.

    SQLite's CURRENT_TIMESTAMP only has one-second resolution, so the model
    sets created_at in Python. This test guards that regression: several
    mutations inside the same second must still order correctly.
    """
    for index in range(4):
        card = create_card(title=f"burst-{index}")
        client.patch(f"/api/cards/{card['id']}/move", json={"column_id": "done", "position": 0})

    activity = client.get("/api/boards/demo/activity").json()
    timestamps = [row["created_at"] for row in activity]

    assert len(activity) == 8
    assert len(set(timestamps)) == len(timestamps), "activity timestamps collided"
    assert timestamps == sorted(timestamps, reverse=True)


def test_activity_is_empty_on_a_fresh_board(client):
    assert client.get("/api/boards/demo/activity").json() == []
