import pytest, json
import app as app_module
from pathlib import Path

@pytest.fixture
def client(tmp_path):
    app_module.OUTPUT_BASE = tmp_path
    app_module._running = False
    app_module._procs = []
    app_module._run_config = {}
    app_module.app.config['TESTING'] = True
    with app_module.app.test_client() as c:
        yield c
    app_module._running = False
    app_module._procs = []

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

def test_api_runs_empty(client):
    r = client.get('/api/runs')
    assert r.status_code == 200
    assert r.get_json() == []

def test_api_runs_with_data(client, tmp_path):
    app_module.OUTPUT_BASE = tmp_path
    q_dir = tmp_path / 'maths' / 'year-12'
    q_dir.mkdir(parents=True)
    questions = [{'question_id': 'q1', 'subject': 'maths', 'year': 'year-12',
                  'question_text': 'test'}]
    (q_dir / 'questions.json').write_text(json.dumps(questions))

    r = client.get('/api/runs')
    data = r.get_json()
    assert len(data) == 1
    assert data[0]['subject'] == 'maths'
    assert data[0]['year'] == 'year-12'
    assert data[0]['count'] == 1

def test_api_questions_returns_list(client, tmp_path):
    app_module.OUTPUT_BASE = tmp_path
    q_dir = tmp_path / 'english' / 'year-9'
    q_dir.mkdir(parents=True)
    questions = [{'question_id': 'q1', 'question_text': 'What is 2+2?'}]
    (q_dir / 'questions.json').write_text(json.dumps(questions))

    r = client.get('/api/questions?subject=english&year=year-9')
    assert r.get_json() == questions

def test_api_questions_missing_params(client):
    r = client.get('/api/questions')
    assert r.get_json() == []

def test_api_questions_missing_file(client):
    r = client.get('/api/questions?subject=science&year=year-7')
    assert r.get_json() == []
