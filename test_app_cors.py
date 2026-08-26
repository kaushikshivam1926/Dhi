try:
    import pytest
    @pytest.fixture
    def client():
        app.config['TESTING'] = True
        with app.test_client() as client:
            yield client
except ImportError:
    pass

from app import app
import os

def test_cors_allowed_origin(client):
    response = client.options('/api/schedule/list', headers={'Origin': 'http://localhost:8080'})
    assert response.headers.get('Access-Control-Allow-Origin') == 'http://localhost:8080'

def test_cors_disallowed_origin(client):
    response = client.options('/api/schedule/list', headers={'Origin': 'http://evil.com'})
    # It shouldn't return '*' or the evil origin
    assert response.headers.get('Access-Control-Allow-Origin') not in ('*', 'http://evil.com')

def test_cors_no_origin(client):
    response = client.options('/api/schedule/list')
    assert response.headers.get('Access-Control-Allow-Origin') != '*'

if __name__ == '__main__':
    app.config['TESTING'] = True
    with app.test_client() as c:
        test_cors_allowed_origin(c)
        test_cors_disallowed_origin(c)
        test_cors_no_origin(c)
    print("All CORS tests passed.")

