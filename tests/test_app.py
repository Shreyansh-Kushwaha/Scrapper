import pytest, json
import app as app_module
from pathlib import Path

@pytest.fixture
def client(tmp_path):
    app_module.OUTPUT_BASE = tmp_path
    app_module._running = False
    app_module._proc = None
    app_module.app.config['TESTING'] = True
    with app_module.app.test_client() as c:
        yield c
    app_module._running = False
    app_module._proc = None

def test_index_returns_html(client):
    r = client.get('/')
    assert r.status_code == 200
    assert b'<html' in r.data.lower()

def test_run_rejects_double_run(client):
    app_module._running = True
    r = client.post('/run', json={
        'subject': 'maths', 'year': 'year-12',
        'username': 'u', 'password': 'p'
    })
    assert r.status_code == 409
    assert r.get_json()['error'] == 'already running'

def test_stop_when_nothing_running(client):
    r = client.post('/stop')
    assert r.status_code == 200
    assert r.get_json()['status'] == 'stopped'
