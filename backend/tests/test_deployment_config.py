"""Deployment-facing configuration checks for the app shell."""

def preflight(client, origin, method):
    return client.options(
        '/api/boards/demo/cards',
        headers={
            'Origin': origin,
            'Access-Control-Request-Method': method,
            'Access-Control-Request-Headers': 'content-type',
        },
    )


def test_cors_allows_configured_local_frontend(client):
    response = preflight(client, 'http://localhost:5173', 'POST')
    assert response.status_code == 200
    assert response.headers.get('access-control-allow-origin') == 'http://localhost:5173'


def test_cors_allows_delete_for_configured_frontend(client):
    response = preflight(client, 'http://localhost:5173', 'DELETE')
    assert response.status_code == 200
    assert response.headers.get('access-control-allow-methods')
    assert 'DELETE' in response.headers['access-control-allow-methods']


def test_cors_does_not_allow_unlisted_origin(client):
    response = preflight(client, 'https://untrusted.example', 'POST')
    assert response.status_code == 400
    assert 'access-control-allow-origin' not in response.headers
