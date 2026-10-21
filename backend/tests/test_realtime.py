"""Integration tests for Member 4's WebSocket event delivery.

Run from backend/: pytest -q tests/test_realtime.py
These exercise the real FastAPI route + test database, not a mocked broadcast.
"""
from app.realtime import manager


def test_two_connected_clients_receive_created_and_moved_events(client):
    with client.websocket_connect('/ws') as first, client.websocket_connect('/ws') as second:
        created_response = client.post(
            '/api/boards/demo/cards',
            json={'title': 'Realtime task', 'description': '', 'column_id': 'todo'},
        )
        assert created_response.status_code == 201
        created_card = created_response.json()

        expected_created = {'type': 'card.created', 'card': created_card}
        assert first.receive_json() == expected_created
        assert second.receive_json() == expected_created

        # The message is broadcast only after persistence: board read sees it.
        board = client.get('/api/boards/demo').json()
        assert created_card['id'] == board['columns'][0]['cards'][0]['id']

        moved_response = client.patch(
            f"/api/cards/{created_card['id']}/move",
            json={'column_id': 'doing', 'position': 0},
        )
        assert moved_response.status_code == 200
        moved_card = moved_response.json()

        expected_moved = {'type': 'card.moved', 'card': moved_card}
        assert first.receive_json() == expected_moved
        assert second.receive_json() == expected_moved
        assert moved_card['column_id'] == 'doing'


def test_websocket_clients_are_removed_after_disconnect(client):
    # A previously closed socket must not linger in the manager or receive later events.
    with client.websocket_connect('/ws') as ws:
        assert ws
        assert len(manager.active_connections) >= 1
    assert len(manager.active_connections) == 0

    response = client.post(
        '/api/boards/demo/cards',
        json={'title': 'After disconnect', 'column_id': 'todo'},
    )
    assert response.status_code == 201
    assert len(manager.active_connections) == 0
