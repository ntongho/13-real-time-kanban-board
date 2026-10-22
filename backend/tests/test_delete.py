"""Card deletion API, persistence, activity, order, and realtime coverage."""
from app.realtime import manager


def create(client, title):
    response = client.post('/api/boards/demo/cards', json={'title': title, 'column_id': 'todo'})
    assert response.status_code == 201
    return response.json()


def test_delete_removes_card_records_activity_and_compacts_positions(client):
    first = create(client, 'Keep first')
    removed = create(client, 'Remove me')
    last = create(client, 'Keep last')

    response = client.delete(f"/api/cards/{removed['id']}")
    assert response.status_code == 204
    assert response.content == b''

    board = client.get('/api/boards/demo').json()
    todo = board['columns'][0]['cards']
    assert [(card['title'], card['position']) for card in todo] == [
        ('Keep first', 0), ('Keep last', 1)
    ]

    activity = client.get('/api/boards/demo/activity').json()
    deletion = activity[0]
    assert deletion['action'] == 'deleted'
    assert deletion['card_id'] == removed['id']
    assert deletion['card_title'] == 'Remove me'
    assert deletion['from_column'] == 'todo'
    assert deletion['message'] == "Deleted 'Remove me' from To Do"
    assert any(row['card_id'] == first['id'] for row in activity)
    assert any(row['card_id'] == last['id'] for row in activity)


def test_delete_unknown_card_returns_404_without_activity(client):
    response = client.delete('/api/cards/not-a-card')
    assert response.status_code == 404
    assert response.json()['detail'] == 'Card not found'
    assert client.get('/api/boards/demo/activity').json() == []


def test_delete_broadcasts_to_two_connected_clients(client):
    card = create(client, 'Realtime delete')
    with client.websocket_connect('/ws') as first, client.websocket_connect('/ws') as second:
        response = client.delete(f"/api/cards/{card['id']}")
        assert response.status_code == 204
        expected = {'type': 'card.deleted', 'card': card}
        assert first.receive_json() == expected
        assert second.receive_json() == expected

    assert manager.active_connections == []
