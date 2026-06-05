# IXL Scraper UI Dashboard — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Flask-based web dashboard to configure, launch, monitor in real-time, and review IXL scrape runs across all subjects (Maths, English, Science) and year groups (Reception–Year 13).

**Architecture:** A single Flask app spawns `ixl_scraper_ui.py` as a subprocess and streams its stdout to the browser via Server-Sent Events. A new unified scraper replaces the existing hardcoded scripts, accepting `--subject` and `--year` arguments and printing structured `[TAG]` progress lines. The frontend is a single HTML page with three tabs driven by vanilla JS.

**Tech Stack:** Python 3.11+, Flask, Playwright (sync API), requests, pytest — no npm/build step.

---

## File Map

| File | Role |
|------|------|
| `requirements.txt` | Python dependencies |
| `progress_parser.py` | Pure function: parse structured `[TAG]` lines → dict |
| `app.py` | Flask app — all routes, SSE streaming, subprocess management |
| `templates/index.html` | Single HTML page, 3 tabs |
| `static/app.js` | SSE listener, tab logic, stats parsing, review tab |
| `ixl_scraper_ui.py` | Unified scraper — all subjects/years/types, structured output |
| `tests/test_progress_parser.py` | Unit tests for progress_parser |
| `tests/test_app.py` | Flask route tests (test client) |
| `output/{subject}/{year}/questions.json` | Scraper output (created at runtime) |
| `output/{subject}/{year}/images/` | Downloaded question images |

---

## Task 1: Setup — dependencies and directory structure

**Files:**
- Create: `requirements.txt`
- Create: `tests/__init__.py`

- [ ] **Step 1: Create requirements.txt**

```
flask>=3.0
playwright>=1.44
requests>=2.31
pytest>=8.0
```

- [ ] **Step 2: Install dependencies**

```bash
pip install -r requirements.txt
playwright install chromium
```

Expected: no errors. `python -c "import flask; import playwright"` exits 0.

- [ ] **Step 3: Create test package and output placeholder**

```bash
mkdir -p tests output templates static
touch tests/__init__.py
```

- [ ] **Step 4: Commit**

```bash
git init
git add requirements.txt tests/__init__.py
git commit -m "chore: project setup and dependencies"
```

---

## Task 2: Progress line parser (TDD)

**Files:**
- Create: `progress_parser.py`
- Create: `tests/test_progress_parser.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_progress_parser.py`:
```python
from progress_parser import parse_line

def test_parse_start():
    r = parse_line('[START] subject=maths year=year-12 total_skills=290')
    assert r == {'type': 'start', 'subject': 'maths', 'year': 'year-12', 'total_skills': 290}

def test_parse_skill():
    r = parse_line('[SKILL] 5/290 Solve linear equations')
    assert r == {'type': 'skill', 'current': 5, 'total': 290, 'name': 'Solve linear equations'}

def test_parse_question():
    r = parse_line('[QUESTION] q=3 format=fill-in-blank')
    assert r == {'type': 'question', 'q': 3, 'format': 'fill-in-blank'}

def test_parse_skip():
    r = parse_line('[SKIP] format=interactive-graph skill=Plot a function')
    assert r == {'type': 'skip', 'format': 'interactive-graph', 'skill': 'Plot a function'}

def test_parse_skill_done():
    r = parse_line('[SKILL_DONE] questions=24')
    assert r == {'type': 'skill_done', 'questions': 24}

def test_parse_done():
    r = parse_line('[DONE] total_questions=5600 elapsed=6420s skipped=23')
    assert r == {'type': 'done', 'total_questions': 5600, 'elapsed': 6420, 'skipped': 23}

def test_parse_error():
    r = parse_line('[ERROR] Login failed — check credentials')
    assert r == {'type': 'error', 'message': 'Login failed — check credentials'}

def test_parse_unknown_returns_none():
    assert parse_line('some random line') is None

def test_parse_empty_returns_none():
    assert parse_line('') is None
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/test_progress_parser.py -v
```

Expected: `ImportError: No module named 'progress_parser'`

- [ ] **Step 3: Implement progress_parser.py**

```python
import re

def parse_line(line):
    line = line.strip()
    if not line:
        return None

    if line.startswith('[START]'):
        m = re.match(r'\[START\] subject=(\S+) year=(\S+) total_skills=(\d+)', line)
        if m:
            return {'type': 'start', 'subject': m.group(1), 'year': m.group(2),
                    'total_skills': int(m.group(3))}

    elif line.startswith('[SKILL]'):
        m = re.match(r'\[SKILL\] (\d+)/(\d+) (.+)', line)
        if m:
            return {'type': 'skill', 'current': int(m.group(1)),
                    'total': int(m.group(2)), 'name': m.group(3)}

    elif line.startswith('[QUESTION]'):
        m = re.match(r'\[QUESTION\] q=(\d+) format=(\S+)', line)
        if m:
            return {'type': 'question', 'q': int(m.group(1)), 'format': m.group(2)}

    elif line.startswith('[SKIP]'):
        m = re.match(r'\[SKIP\] format=(\S+) skill=(.+)', line)
        if m:
            return {'type': 'skip', 'format': m.group(1), 'skill': m.group(2)}

    elif line.startswith('[SKILL_DONE]'):
        m = re.match(r'\[SKILL_DONE\] questions=(\d+)', line)
        if m:
            return {'type': 'skill_done', 'questions': int(m.group(1))}

    elif line.startswith('[DONE]'):
        m = re.match(r'\[DONE\] total_questions=(\d+) elapsed=(\d+)s skipped=(\d+)', line)
        if m:
            return {'type': 'done', 'total_questions': int(m.group(1)),
                    'elapsed': int(m.group(2)), 'skipped': int(m.group(3))}

    elif line.startswith('[ERROR]'):
        return {'type': 'error', 'message': line[7:].strip()}

    return None
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
pytest tests/test_progress_parser.py -v
```

Expected: 9 passed.

- [ ] **Step 5: Commit**

```bash
git add progress_parser.py tests/test_progress_parser.py
git commit -m "feat: progress line parser with tests"
```

---

## Task 3: Flask skeleton — /, /run, /stop

**Files:**
- Create: `app.py`
- Create: `tests/test_app.py`

- [ ] **Step 1: Write failing tests**

`tests/test_app.py`:
```python
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
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/test_app.py -v
```

Expected: `ImportError: No module named 'app'`

- [ ] **Step 3: Create app.py with skeleton routes**

```python
from flask import Flask, Response, request, jsonify, render_template, stream_with_context
import json, subprocess, threading, os
from pathlib import Path

app = Flask(__name__)
OUTPUT_BASE = Path(os.environ.get('IXL_OUTPUT_DIR', 'output'))

_proc = None
_running = False
_lock = threading.Lock()


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/run', methods=['POST'])
def run():
    global _proc, _running
    with _lock:
        if _running:
            return jsonify({'error': 'already running'}), 409
        data = request.get_json()
        subject  = data['subject']
        year     = data['year']
        username = data['username']
        password = data['password']
        max_q    = str(data.get('max_questions', 0))
        headless = data.get('headless', True)

        output_dir = OUTPUT_BASE / subject / year
        output_dir.mkdir(parents=True, exist_ok=True)

        cmd = [
            'python3', 'ixl_scraper_ui.py',
            '--subject', subject,
            '--year',    year,
            '--username', username,
            '--password', password,
            '--max-questions', max_q,
            '--output-dir', str(output_dir),
        ]
        if headless:
            cmd.append('--headless')

        _proc    = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, text=True, bufsize=1)
        _running = True
        return jsonify({'status': 'started'})


@app.route('/stop', methods=['POST'])
def stop():
    global _proc, _running
    if _proc is not None:
        _proc.kill()
        _proc = None
    with _lock:
        _running = False
    return jsonify({'status': 'stopped'})


@app.route('/stream')
def stream():
    def generate():
        global _proc, _running
        if _proc is None:
            yield 'data: [ERROR] No scraper running\n\n'
            return
        for line in _proc.stdout:
            yield f'data: {line.rstrip()}\n\n'
        rc = _proc.wait()
        if rc != 0:
            yield f'data: [ERROR] scraper exited with code {rc}\n\n'
        with _lock:
            _running = False
    return Response(stream_with_context(generate()), mimetype='text/event-stream',
                    headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})


if __name__ == '__main__':
    app.run(debug=True, port=5000, threaded=True)
```

- [ ] **Step 4: Create a minimal templates/index.html so the / route works**

`templates/index.html`:
```html
<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><title>IXL Scraper</title></head>
<body><h1>IXL Scraper Dashboard</h1></body></html>
```

- [ ] **Step 5: Run tests**

```bash
pytest tests/test_app.py -v
```

Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add app.py templates/index.html tests/test_app.py
git commit -m "feat: Flask skeleton with run/stop/stream routes"
```

---

## Task 4: Flask review API — /api/runs and /api/questions

**Files:**
- Modify: `app.py` — add two routes
- Modify: `tests/test_app.py` — add API tests

- [ ] **Step 1: Add failing tests to tests/test_app.py**

Append to `tests/test_app.py`:
```python
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
```

- [ ] **Step 2: Run failing tests**

```bash
pytest tests/test_app.py -v -k "api"
```

Expected: 5 failures with `404` or attribute errors.

- [ ] **Step 3: Add /api/runs and /api/questions to app.py**

Add these two routes to `app.py` (before `if __name__ == '__main__':`):

```python
@app.route('/api/runs')
def api_runs():
    runs = []
    if OUTPUT_BASE.exists():
        for subject_dir in sorted(OUTPUT_BASE.iterdir()):
            if not subject_dir.is_dir():
                continue
            for year_dir in sorted(subject_dir.iterdir()):
                if not year_dir.is_dir():
                    continue
                qfile = year_dir / 'questions.json'
                if qfile.exists():
                    try:
                        count = len(json.loads(qfile.read_text(encoding='utf-8')))
                    except Exception:
                        count = 0
                    runs.append({
                        'subject': subject_dir.name,
                        'year':    year_dir.name,
                        'count':   count,
                    })
    return jsonify(runs)


@app.route('/api/questions')
def api_questions():
    subject = request.args.get('subject', '')
    year    = request.args.get('year', '')
    if not subject or not year:
        return jsonify([])
    qfile = OUTPUT_BASE / subject / year / 'questions.json'
    if not qfile.exists():
        return jsonify([])
    try:
        return jsonify(json.loads(qfile.read_text(encoding='utf-8')))
    except Exception:
        return jsonify([])
```

- [ ] **Step 4: Run all tests**

```bash
pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add app.py tests/test_app.py
git commit -m "feat: add /api/runs and /api/questions review endpoints"
```

---

## Task 5: Frontend HTML — index.html (3-tab layout)

**Files:**
- Modify: `templates/index.html` — replace stub with full 3-tab page

- [ ] **Step 1: Replace templates/index.html with the full page**

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>IXL Scraper Dashboard</title>
  <script src="/static/app.js" defer></script>
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    body { background: #0f172a; color: #f1f5f9; font-family: system-ui, sans-serif; min-height: 100vh; }
    header { padding: 16px 32px; border-bottom: 1px solid #1e293b; display: flex; align-items: center; gap: 12px; }
    header h1 { font-size: 18px; font-weight: 700; }
    .tabs { display: flex; gap: 4px; padding: 20px 32px 0; }
    .tab-btn { padding: 10px 20px; border: none; border-radius: 8px 8px 0 0; cursor: pointer; font-size: 14px; font-weight: 500; background: #1e293b; color: #94a3b8; transition: background .15s; }
    .tab-btn.active { background: #6366f1; color: #fff; font-weight: 600; }
    .tab-panel { display: none; padding: 0 32px 32px; }
    .tab-panel.active { display: block; }
    .card { background: #1e293b; border-radius: 12px; padding: 24px; margin-top: 20px; }
    .form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
    .field { display: flex; flex-direction: column; gap: 6px; }
    label { font-size: 11px; text-transform: uppercase; letter-spacing: .05em; color: #64748b; }
    select, input[type=text], input[type=password], input[type=number] {
      background: #0f172a; color: #f1f5f9; border: 1px solid #334155;
      border-radius: 6px; padding: 9px 12px; font-size: 14px; width: 100%;
    }
    select:focus, input:focus { outline: 2px solid #6366f1; border-color: transparent; }
    .toggle-row { display: flex; align-items: center; gap: 10px; margin-top: 4px; }
    .toggle-row input[type=checkbox] { width: 16px; height: 16px; cursor: pointer; }
    .btn { padding: 10px 28px; border: none; border-radius: 8px; font-size: 14px; font-weight: 600; cursor: pointer; }
    .btn-primary { background: #6366f1; color: #fff; }
    .btn-primary:disabled { background: #334155; color: #64748b; cursor: not-allowed; }
    .btn-danger  { background: #dc2626; color: #fff; }
    .btn-secondary { background: #334155; color: #f1f5f9; border: 1px solid #475569; }
    .run-actions { display: flex; align-items: center; gap: 16px; margin-top: 24px; }
    #status-text { font-size: 13px; color: #64748b; }
    .stats-bar { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-top: 20px; }
    .stat-card { background: #1e293b; border-radius: 10px; padding: 16px 20px; text-align: center; }
    .stat-label { font-size: 11px; text-transform: uppercase; letter-spacing: .05em; color: #64748b; }
    .stat-value { font-size: 28px; font-weight: 700; margin-top: 4px; }
    #log-panel { background: #020617; border-radius: 10px; padding: 16px; font-family: monospace; font-size: 12px; height: 340px; overflow-y: auto; margin-top: 20px; line-height: 1.6; }
    .log-skill  { color: #818cf8; }
    .log-skip   { color: #f59e0b; }
    .log-error  { color: #ef4444; }
    .log-done   { color: #10b981; }
    .log-plain  { color: #cbd5e1; }
    .stop-row   { margin-top: 12px; display: flex; align-items: center; gap: 12px; }
    .review-controls { display: flex; gap: 10px; flex-wrap: wrap; align-items: center; margin-top: 20px; }
    .review-controls select, .review-controls input { width: auto; min-width: 160px; }
    #search-input { flex: 1; min-width: 200px; }
    table { width: 100%; border-collapse: collapse; font-size: 13px; margin-top: 16px; }
    th { color: #64748b; font-size: 11px; text-transform: uppercase; letter-spacing: .05em; text-align: left; padding: 8px 12px; border-bottom: 1px solid #334155; }
    td { padding: 9px 12px; border-bottom: 1px solid #1e293b; color: #cbd5e1; }
    tr:nth-child(even) td { background: #0f172a; }
    .badge { padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 600; }
    .badge-mcq   { background: #4c1d95; color: #ddd6fe; }
    .badge-fill  { background: #1e3a8a; color: #bfdbfe; }
    .badge-other { background: #1c3826; color: #6ee7b7; }
    td.skill-cell { color: #818cf8; }
    #review-count { font-size: 13px; color: #64748b; margin-top: 8px; }
    .error-banner { background: #7f1d1d; border: 1px solid #991b1b; border-radius: 8px; padding: 12px 16px; font-size: 13px; color: #fca5a5; margin-top: 12px; display: none; }
  </style>
</head>
<body>
  <header>
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#6366f1" stroke-width="2"><circle cx="12" cy="12" r="10"/><path d="M12 8v4l3 3"/></svg>
    <h1>IXL Scraper Dashboard</h1>
  </header>

  <div class="tabs">
    <button class="tab-btn active" data-tab="configure">⚙️ Configure &amp; Launch</button>
    <button class="tab-btn" data-tab="progress">📡 Live Progress</button>
    <button class="tab-btn" data-tab="review">🔍 Review Data</button>
  </div>

  <!-- ── Tab 1: Configure ── -->
  <div id="tab-configure" class="tab-panel active">
    <div class="card">
      <form id="run-form" autocomplete="off">
        <div class="form-grid">
          <div class="field">
            <label for="subject">Subject</label>
            <select id="subject" name="subject">
              <option value="maths">Maths</option>
              <option value="english">English</option>
              <option value="science">Science</option>
            </select>
          </div>
          <div class="field">
            <label for="year">Year Group</label>
            <select id="year" name="year">
              <option value="reception">Reception</option>
              <option value="year-1">Year 1</option>
              <option value="year-2">Year 2</option>
              <option value="year-3">Year 3</option>
              <option value="year-4">Year 4</option>
              <option value="year-5">Year 5</option>
              <option value="year-6">Year 6</option>
              <option value="year-7">Year 7</option>
              <option value="year-8">Year 8</option>
              <option value="year-9">Year 9</option>
              <option value="year-10">Year 10</option>
              <option value="year-11">Year 11</option>
              <option value="year-12">Year 12</option>
              <option value="year-13">Year 13</option>
            </select>
          </div>
          <div class="field">
            <label for="username">IXL Username</label>
            <input type="text" id="username" name="username" placeholder="e.g. supersheldon1">
          </div>
          <div class="field">
            <label for="password">IXL Password</label>
            <input type="password" id="password" name="password" placeholder="Required">
          </div>
          <div class="field">
            <label for="max-questions">Max Questions per Skill</label>
            <input type="number" id="max-questions" name="max_questions" value="0" min="0">
            <span style="font-size:11px;color:#475569;margin-top:2px;">0 = auto-stop on repeat detection</span>
          </div>
          <div class="field">
            <label>Headless Mode</label>
            <div class="toggle-row">
              <input type="checkbox" id="headless" name="headless" checked>
              <span style="font-size:13px;color:#94a3b8;">Run browser in background</span>
            </div>
          </div>
        </div>
        <div class="run-actions">
          <button type="submit" class="btn btn-primary" id="run-btn">▶ Run Scraper</button>
          <span id="status-text">No scraper running</span>
        </div>
        <div class="error-banner" id="run-error"></div>
      </form>
    </div>
  </div>

  <!-- ── Tab 2: Progress ── -->
  <div id="tab-progress" class="tab-panel">
    <div class="stats-bar">
      <div class="stat-card">
        <div class="stat-label">Skills Done</div>
        <div class="stat-value" id="stat-skills">—</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Questions Found</div>
        <div class="stat-value" style="color:#10b981" id="stat-questions">—</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Skipped</div>
        <div class="stat-value" style="color:#f59e0b" id="stat-skipped">—</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Est. Time Left</div>
        <div class="stat-value" id="stat-time">—</div>
      </div>
    </div>
    <div id="log-panel"></div>
    <div class="stop-row">
      <button class="btn btn-danger" id="stop-btn">⬛ Stop Scraper</button>
      <span id="run-label" style="font-size:13px;color:#64748b;"></span>
    </div>
  </div>

  <!-- ── Tab 3: Review ── -->
  <div id="tab-review" class="tab-panel">
    <div class="review-controls">
      <select id="run-selector"><option value="">— Select a completed run —</option></select>
      <select id="format-filter">
        <option value="">All formats</option>
        <option value="fill-in-blank">Fill in Blank</option>
        <option value="multiple-choice">Multiple Choice</option>
        <option value="word-bank">Word Bank</option>
        <option value="click-to-select">Click to Select</option>
        <option value="sort/sequence">Sort / Sequence</option>
        <option value="drag-and-drop">Drag and Drop</option>
        <option value="matching">Matching</option>
      </select>
      <input type="text" id="search-input" placeholder="Search questions…">
      <button class="btn btn-secondary" id="export-btn">Export CSV</button>
    </div>
    <div id="review-count"></div>
    <div style="overflow-x:auto">
      <table id="review-table">
        <thead>
          <tr>
            <th>Skill</th>
            <th>Format</th>
            <th>Question</th>
            <th>Answer</th>
            <th>Img</th>
          </tr>
        </thead>
        <tbody id="review-tbody"></tbody>
      </table>
    </div>
  </div>
</body>
</html>
```

- [ ] **Step 2: Verify Flask serves the page**

```bash
python3 app.py &
curl -s http://localhost:5000/ | grep -i "ixl scraper"
kill %1
```

Expected: output contains `IXL Scraper Dashboard`.

- [ ] **Step 3: Commit**

```bash
git add templates/index.html
git commit -m "feat: 3-tab dashboard HTML layout"
```

---

## Task 6: Frontend JS — tab switching, form submit, SSE streaming, stop

**Files:**
- Create: `static/app.js`

- [ ] **Step 1: Create static/app.js**

```javascript
// ── State ──────────────────────────────────────────────────────────────────────
let _es = null;          // EventSource
let _running = false;
let _skillsTotal = 0;
let _skillsDone  = 0;
let _questions   = 0;
let _skipped     = 0;
let _startTime   = 0;

// ── Tab switching ──────────────────────────────────────────────────────────────
document.querySelectorAll('.tab-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    const tab = btn.dataset.tab;
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
    btn.classList.add('active');
    document.getElementById('tab-' + tab).classList.add('active');
    if (tab === 'review') loadRuns();
  });
});

// ── Form submit → POST /run ────────────────────────────────────────────────────
document.getElementById('run-form').addEventListener('submit', async e => {
  e.preventDefault();
  const password = document.getElementById('password').value.trim();
  if (!password) {
    showError('Password is required.');
    return;
  }
  clearError();

  const payload = {
    subject:       document.getElementById('subject').value,
    year:          document.getElementById('year').value,
    username:      document.getElementById('username').value.trim(),
    password:      password,
    max_questions: parseInt(document.getElementById('max-questions').value, 10),
    headless:      document.getElementById('headless').checked,
  };

  const res = await fetch('/run', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(payload),
  });
  const data = await res.json();

  if (!res.ok) {
    showError(data.error || 'Failed to start scraper.');
    return;
  }

  setRunning(true, payload.subject, payload.year);
  switchTab('progress');
  openStream();
});

// ── SSE streaming ──────────────────────────────────────────────────────────────
function openStream() {
  if (_es) { _es.close(); _es = null; }
  resetStats();
  _es = new EventSource('/stream');

  _es.onmessage = e => {
    const line = e.data;
    appendLog(line);
    parseStats(line);
  };

  _es.onerror = () => {
    _es.close();
    _es = null;
    setRunning(false);
  };
}

function parseStats(line) {
  if (line.startsWith('[START]')) {
    const m = line.match(/total_skills=(\d+)/);
    if (m) { _skillsTotal = parseInt(m[1]); _startTime = Date.now(); }
    updateStatCards();
  } else if (line.startsWith('[SKILL_DONE]')) {
    _skillsDone++;
    const m = line.match(/questions=(\d+)/);
    if (m) _questions += parseInt(m[1]);
    updateStatCards();
    updateTimeLeft();
  } else if (line.startsWith('[SKIP]')) {
    _skipped++;
    updateStatCards();
  } else if (line.startsWith('[QUESTION]')) {
    // individual question found — update running total from [SKILL_DONE] instead
  } else if (line.startsWith('[DONE]') || line.startsWith('[ERROR]')) {
    _es && _es.close();
    _es = null;
    setRunning(false);
  }
}

function updateStatCards() {
  document.getElementById('stat-skills').textContent =
    _skillsTotal ? `${_skillsDone} / ${_skillsTotal}` : `${_skillsDone}`;
  document.getElementById('stat-questions').textContent = _questions;
  document.getElementById('stat-skipped').textContent   = _skipped;
}

function updateTimeLeft() {
  if (!_skillsDone || !_skillsTotal) return;
  const elapsed  = (Date.now() - _startTime) / 1000;
  const remaining = (_skillsTotal - _skillsDone) * (elapsed / _skillsDone);
  document.getElementById('stat-time').textContent = fmtSeconds(remaining);
}

function fmtSeconds(s) {
  if (s < 60)  return `${Math.round(s)}s`;
  if (s < 3600) return `${Math.round(s / 60)}m`;
  const h = Math.floor(s / 3600);
  const m = Math.round((s % 3600) / 60);
  return `${h}h ${m}m`;
}

function resetStats() {
  _skillsTotal = _skillsDone = _questions = _skipped = _startTime = 0;
  ['stat-skills','stat-questions','stat-skipped','stat-time'].forEach(id => {
    document.getElementById(id).textContent = '—';
  });
  document.getElementById('log-panel').innerHTML = '';
}

// ── Log panel ──────────────────────────────────────────────────────────────────
function appendLog(line) {
  const panel = document.getElementById('log-panel');
  const span  = document.createElement('div');
  if      (line.startsWith('[SKILL]'))      span.className = 'log-skill';
  else if (line.startsWith('[SKIP]'))       span.className = 'log-skip';
  else if (line.startsWith('[ERROR]'))      span.className = 'log-error';
  else if (line.startsWith('[DONE]'))       span.className = 'log-done';
  else                                      span.className = 'log-plain';
  span.textContent = line;
  panel.appendChild(span);
  panel.scrollTop = panel.scrollHeight;
}

// ── Stop button ───────────────────────────────────────────────────────────────
document.getElementById('stop-btn').addEventListener('click', async () => {
  if (_es) { _es.close(); _es = null; }
  await fetch('/stop', {method: 'POST'});
  setRunning(false);
});

// ── UI helpers ─────────────────────────────────────────────────────────────────
function setRunning(yes, subject='', year='') {
  _running = yes;
  document.getElementById('run-btn').disabled = yes;
  document.getElementById('status-text').textContent = yes
    ? `Running: ${subject} ${year}` : 'No scraper running';
  document.getElementById('run-label').textContent = yes
    ? `Scraping ${subject} / ${year}` : '';
}

function switchTab(name) {
  document.querySelectorAll('.tab-btn').forEach(b =>
    b.classList.toggle('active', b.dataset.tab === name));
  document.querySelectorAll('.tab-panel').forEach(p =>
    p.classList.toggle('active', p.id === 'tab-' + name));
}

function showError(msg) {
  const el = document.getElementById('run-error');
  el.textContent = msg;
  el.style.display = 'block';
}
function clearError() {
  document.getElementById('run-error').style.display = 'none';
}
```

- [ ] **Step 2: Verify the page loads without JS errors**

```bash
python3 app.py &
# Open http://localhost:5000 in a browser and check browser console for errors
kill %1
```

Expected: no console errors, tabs switch on click.

- [ ] **Step 3: Commit**

```bash
git add static/app.js
git commit -m "feat: SSE streaming, tab logic, run/stop UI"
```

---

## Task 7: Frontend JS — review tab

**Files:**
- Modify: `static/app.js` — append review tab functions

- [ ] **Step 1: Append to static/app.js**

```javascript
// ── Review tab ────────────────────────────────────────────────────────────────
let _allQuestions = [];

async function loadRuns() {
  const res  = await fetch('/api/runs');
  const runs = await res.json();
  const sel  = document.getElementById('run-selector');
  sel.innerHTML = '<option value="">— Select a completed run —</option>';
  runs.forEach(r => {
    const opt = document.createElement('option');
    opt.value = `${r.subject}|${r.year}`;
    opt.textContent = `${r.subject} / ${r.year}  (${r.count} questions)`;
    sel.appendChild(opt);
  });
}

document.getElementById('run-selector').addEventListener('change', async e => {
  const [subject, year] = (e.target.value || '').split('|');
  if (!subject || !year) { _allQuestions = []; renderTable([]); return; }
  const res = await fetch(`/api/questions?subject=${subject}&year=${year}`);
  _allQuestions = await res.json();
  renderFiltered();
});

document.getElementById('format-filter').addEventListener('change', renderFiltered);
document.getElementById('search-input').addEventListener('input', renderFiltered);

function renderFiltered() {
  const fmt    = document.getElementById('format-filter').value.toLowerCase();
  const search = document.getElementById('search-input').value.toLowerCase();
  const rows   = _allQuestions.filter(q => {
    const fmtOk    = !fmt    || (q.format || '').toLowerCase().includes(fmt);
    const searchOk = !search || (q.question_text || '').toLowerCase().includes(search)
                              || (q.skill_name   || '').toLowerCase().includes(search);
    return fmtOk && searchOk;
  });
  renderTable(rows);
}

function renderTable(rows) {
  const tbody = document.getElementById('review-tbody');
  tbody.innerHTML = '';
  rows.forEach(q => {
    const tr   = document.createElement('tr');
    const fmt  = (q.format || 'other').toLowerCase();
    const badgeCls = fmt.includes('multiple') ? 'badge-mcq'
                   : fmt.includes('fill')     ? 'badge-fill'
                   : 'badge-other';
    tr.innerHTML = `
      <td class="skill-cell">${esc(q.skill_name || '')}</td>
      <td><span class="badge ${badgeCls}">${esc(q.format || 'other')}</span></td>
      <td>${esc((q.question_text || '').slice(0, 120))}</td>
      <td style="color:#10b981">${esc(q.correct_answer || '')}</td>
      <td style="text-align:center">${q.has_image ? '🖼' : ''}</td>`;
    tbody.appendChild(tr);
  });
  document.getElementById('review-count').textContent =
    `${rows.length} of ${_allQuestions.length} questions`;
}

function esc(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

// ── CSV export ─────────────────────────────────────────────────────────────────
document.getElementById('export-btn').addEventListener('click', () => {
  const fmt    = document.getElementById('format-filter').value.toLowerCase();
  const search = document.getElementById('search-input').value.toLowerCase();
  const rows   = _allQuestions.filter(q => {
    const fmtOk    = !fmt    || (q.format || '').toLowerCase().includes(fmt);
    const searchOk = !search || (q.question_text || '').toLowerCase().includes(search)
                              || (q.skill_name   || '').toLowerCase().includes(search);
    return fmtOk && searchOk;
  });
  if (!rows.length) return;

  const cols = ['question_id','subject','year','skill_name','format','question_text','correct_answer','has_image'];
  const csv  = [cols.join(','), ...rows.map(q =>
    cols.map(c => `"${String(q[c] ?? '').replace(/"/g, '""')}"`).join(',')
  )].join('\n');

  const a   = document.createElement('a');
  a.href    = 'data:text/csv;charset=utf-8,' + encodeURIComponent(csv);
  a.download = 'ixl_questions.csv';
  a.click();
});
```

- [ ] **Step 2: Manual test — create a fixture JSON and verify the review tab**

```bash
mkdir -p output/maths/year-12
cat > output/maths/year-12/questions.json << 'EOF'
[{"question_id":"q1","subject":"maths","year":"year-12","skill_name":"Solve linear equations",
  "format":"fill-in-blank","question_text":"Solve for x. 3x + 7 = 22. x =",
  "correct_answer":"5","has_image":false,"image_paths":[]}]
EOF
python3 app.py &
# Open http://localhost:5000, click Review Data, select "maths / year-12"
# Verify the question row appears, search works, CSV downloads
kill %1
```

Expected: row visible, filter works, CSV contains correct headers.

- [ ] **Step 3: Commit**

```bash
git add static/app.js
git commit -m "feat: review tab with filter, search, and CSV export"
```

---

## Task 8: Unified scraper — argparse + login + skill discovery

**Files:**
- Create: `ixl_scraper_ui.py`

- [ ] **Step 1: Create ixl_scraper_ui.py with argparse, login, and skill discovery**

```python
#!/usr/bin/env python3
"""
IXL Unified Scraper — all subjects, all year groups
Prints structured [TAG] progress lines for the Flask UI.

Usage:
  python3 ixl_scraper_ui.py --subject maths --year year-12 \
    --username supersheldon1 --password "..." \
    --max-questions 0 --output-dir output/maths/year-12 --headless
"""
import argparse, json, re, time, hashlib, requests, sys
from pathlib import Path
from datetime import datetime, timezone
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

BASE_URL   = "https://uk.ixl.com"
LOGIN_URL  = f"{BASE_URL}/signin"

SKIP_ALTS = {
    "Scratchpad","Eraser","Highlighter - blue","Highlighter - yellow",
    "Highlighter - pink","Pencil - black","Pencil - blue","Pencil - red",
    "Pencil - green","Ruler","Protractor","Calculator"
}

SKIP_FORMATS = {'audio', 'interactive-graph', 'graph-interaction', 'canvas'}

TYPE_MAP = {
    "MULTIPLE_CHOICE":   "multiple-choice",
    "FILL_IN_THE_BLANK": "fill-in-blank",
    "FILL_IN":           "fill-in-blank",
    "WORD_BANK":         "word-bank",
    "CLICK_ON":          "click-to-select",
    "SORT":              "sort/sequence",
    "SEQUENCE":          "sort/sequence",
    "DRAG":              "drag-and-drop",
    "ORDER":             "ordering",
    "MATCH":             "matching",
    "SELECT":            "select-from-dropdown",
    "UNDERLINE":         "underline/highlight",
    "AUDIO":             "audio",
    "GRAPH_INTERACTION": "graph-interaction",
    "INTERACTIVE_GRAPH": "interactive-graph",
    "CANVAS":            "canvas",
}


# ── Progress output ────────────────────────────────────────────────────────────

def p_start(subject, year, total):
    print(f"[START] subject={subject} year={year} total_skills={total}", flush=True)

def p_skill(i, total, name):
    print(f"[SKILL] {i}/{total} {name}", flush=True)

def p_question(q, fmt):
    print(f"[QUESTION] q={q} format={fmt}", flush=True)

def p_skip(fmt, skill):
    print(f"[SKIP] format={fmt} skill={skill}", flush=True)

def p_skill_done(questions):
    print(f"[SKILL_DONE] questions={questions}", flush=True)

def p_done(total_q, elapsed, skipped):
    print(f"[DONE] total_questions={total_q} elapsed={int(elapsed)}s skipped={skipped}", flush=True)

def p_error(msg):
    print(f"[ERROR] {msg}", flush=True)


# ── Utilities ──────────────────────────────────────────────────────────────────

def clean(t):
    return re.sub(r"\s+", " ", t or "").strip()

def make_question_id(subject, year, skill_name, q_index):
    slug = re.sub(r"[^a-z0-9]+", "-", skill_name.lower()).strip("-")
    return f"ixl-{subject}-{year}-{slug}-q{q_index}"

def detect_type(html):
    for token, label in TYPE_MAP.items():
        if token in html:
            return label
    return "other"

def should_skip(qtype):
    return any(s in qtype for s in SKIP_FORMATS)


# ── Login ──────────────────────────────────────────────────────────────────────

def login(page, username, password):
    print(f"Logging in as {username} ...", flush=True)
    page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=20000)
    time.sleep(1.5)
    page.fill("#siusername", username)
    time.sleep(0.3)
    page.fill("#sipassword", password)
    time.sleep(0.3)
    page.click("button.submit-button[type='submit']")
    time.sleep(4)

    if page.query_selector(".subaccount-selection-form"):
        page.evaluate(
            "document.querySelector('[data-cy=\"subaccount-selection-Child 1\"] "
            ".signin-avatar').click()"
        )
        time.sleep(3)

    ok = "Student Dashboard" in page.title() or "signin" not in page.url.lower()
    if not ok:
        p_error("Login failed — check credentials")
        return False
    print("Login OK", flush=True)
    return True


# ── Skill discovery ────────────────────────────────────────────────────────────

def get_skills(page, subject, year):
    index_url = f"{BASE_URL}/{subject}/{year}"
    print(f"Loading skill index: {index_url}", flush=True)
    page.goto(index_url, wait_until="networkidle", timeout=30000)
    time.sleep(2)

    skills = []
    seen   = set()
    path_fragment = f"/{subject}/{year}/"

    for a in page.query_selector_all("a[href]"):
        try:
            href = a.get_attribute("href") or ""
            name = clean(a.inner_text())
            if path_fragment in href and href not in seen and name:
                url = href if href.startswith("http") else f"{BASE_URL}{href}"
                skills.append({"name": name, "url": url})
                seen.add(href)
        except Exception:
            pass

    print(f"Found {len(skills)} skills.", flush=True)
    return skills
```

- [ ] **Step 2: Quick smoke test — verify argparse works**

```bash
python3 ixl_scraper_ui.py --help
```

Expected: usage message listing `--subject`, `--year`, etc. (argparse not yet added — this confirms it's missing, see next step).

- [ ] **Step 3: Add argparse main() stub to ixl_scraper_ui.py**

Append to `ixl_scraper_ui.py`:

```python
# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="IXL Unified Scraper")
    parser.add_argument("--subject",       required=True, choices=["maths","english","science"])
    parser.add_argument("--year",          required=True)
    parser.add_argument("--username",      required=True)
    parser.add_argument("--password",      required=True)
    parser.add_argument("--max-questions", type=int, default=0)
    parser.add_argument("--output-dir",    required=True)
    parser.add_argument("--headless",      action="store_true")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    img_dir = output_dir / "images"
    img_dir.mkdir(exist_ok=True)

    start_time = time.time()

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=args.headless,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        ctx = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="en-GB",
            viewport={"width": 1280, "height": 900},
        )
        page = ctx.new_page()

        if not login(page, args.username, args.password):
            browser.close()
            sys.exit(1)

        skills = get_skills(page, args.subject, args.year)
        if not skills:
            p_error("No skills found on index page")
            browser.close()
            sys.exit(1)

        p_start(args.subject, args.year, len(skills))

        all_questions = []
        total_skipped = 0

        for i, skill in enumerate(skills, 1):
            p_skill(i, len(skills), skill["name"])
            qs, skipped = scrape_skill(
                page, skill, args.subject, args.year,
                args.max_questions, img_dir
            )
            total_skipped += skipped
            all_questions.extend(qs)
            p_skill_done(len(qs))

            # Write incrementally so progress is visible if interrupted
            (output_dir / "questions.json").write_text(
                json.dumps(all_questions, indent=2, ensure_ascii=False),
                encoding="utf-8"
            )

        browser.close()

    elapsed = time.time() - start_time
    p_done(len(all_questions), elapsed, total_skipped)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Verify argparse works**

```bash
python3 ixl_scraper_ui.py --help
```

Expected: usage message with all arguments listed.

- [ ] **Step 5: Commit**

```bash
git add ixl_scraper_ui.py
git commit -m "feat: unified scraper skeleton with login and skill discovery"
```

---

## Task 9: Unified scraper — question extraction + answer capture

**Files:**
- Modify: `ixl_scraper_ui.py` — add extraction and answer-capture functions

- [ ] **Step 1: Add helper and extraction functions to ixl_scraper_ui.py (before main())**

```python
# ── Interaction helpers ────────────────────────────────────────────────────────

def click_crisp(page, label):
    for b in page.query_selector_all("button.crisp-button"):
        if (b.inner_text() or "").strip() == label and b.bounding_box():
            try:
                b.scroll_into_view_if_needed()
                time.sleep(0.1)
                b.click(force=True, timeout=4000)
                return True
            except Exception:
                pass
    return False


def get_question_text(page):
    qc = page.query_selector(".question-component")
    return clean(qc.inner_text() if qc else "")


def extract_choices(page, qtype):
    choices = []
    if "multiple-choice" in qtype:
        els = page.query_selector_all(
            "[class*='SelectableTile'][class*='MULTIPLE_CHOICE']:not([class*='nonInteractive'])"
        )
        choices = [clean(e.inner_text()) for e in els if clean(e.inner_text())]

    elif "word-bank" in qtype:
        for sel in ["[class*='WORD_BANK'] [class*='tile']",
                    "[class*='wordBank'] span", "[class*='word-bank'] span"]:
            found = [clean(e.inner_text()) for e in page.query_selector_all(sel)
                     if clean(e.inner_text())]
            if found: choices = found; break

    elif "click-to-select" in qtype or "underline" in qtype:
        for sel in ["[class*='CLICK_ON']", "[class*='token']", "[class*='clickable']"]:
            found = [clean(e.inner_text()) for e in page.query_selector_all(sel)
                     if clean(e.inner_text())]
            if found: choices = found; break

    elif any(k in qtype for k in ("drag", "sort", "order", "match", "sequence")):
        for sel in ["[draggable='true']", "[class*='drag-item']", "[class*='draggable']"]:
            found = [clean(e.inner_text()) for e in page.query_selector_all(sel)
                     if clean(e.inner_text())]
            if found: choices = found; break

    elif "select-from-dropdown" in qtype:
        for sel in ["select option", "[class*='dropdown'] [class*='option']"]:
            found = [clean(e.inner_text()) for e in page.query_selector_all(sel)
                     if clean(e.inner_text())]
            if found: choices = found; break

    return choices


def capture_answer(page, qtype):
    """Submit a wrong answer and read the correct answer from .correct-answer."""
    # Submit wrong answer
    if "multiple-choice" in qtype:
        try:
            page.locator(
                "[class*='SelectableTile'][class*='MULTIPLE_CHOICE']"
                ":not([class*='nonInteractive'])"
            ).first.click(force=True, timeout=5000)
            time.sleep(0.4)
        except Exception:
            pass
    else:
        for inp in page.query_selector_all("input[type='text'], input[type='number']"):
            try:
                if inp.is_visible():
                    inp.fill("zzz")
                    break
            except Exception:
                pass

    if not click_crisp(page, "Submit"):
        page.keyboard.press("Enter")
    time.sleep(1.5)

    # Read correct answer
    correct = ""
    try:
        page.wait_for_selector(".correct-answer", timeout=5000)
        ca = page.query_selector(".correct-answer")
        if ca:
            if "multiple-choice" in qtype:
                tile = ca.query_selector("[class*='SelectableTile']")
                if tile:
                    txt = clean(tile.inner_text())
                    correct = re.sub(r"^Correct answer,?\s*", "", txt).strip()
            else:
                inp = ca.query_selector("input.fillIn")
                if inp:
                    correct = inp.get_attribute("value") or ""
                if not correct:
                    correct = clean(ca.inner_text())
    except Exception:
        pass

    # Dismiss feedback
    for label in ("Got it", "Next", "Continue", "OK"):
        if click_crisp(page, label):
            time.sleep(0.8)
            break

    return correct


def wait_for_new_question(page, prev_text):
    deadline = time.time() + 8
    while time.time() < deadline:
        current = get_question_text(page)
        if (current and len(current) > 20
                and not current.startswith("Submit")
                and current[:80] != prev_text[:80]):
            return True
        for label in ("Got it", "Next", "Continue"):
            if click_crisp(page, label):
                time.sleep(0.5)
                break
        time.sleep(0.4)
    return False
```

- [ ] **Step 2: Commit the extraction helpers**

```bash
git add ixl_scraper_ui.py
git commit -m "feat: question extraction and answer capture helpers"
```

---

## Task 10: Unified scraper — image download + repeat detection + scrape_skill

**Files:**
- Modify: `ixl_scraper_ui.py` — add image downloader and scrape_skill()

- [ ] **Step 1: Add image downloader to ixl_scraper_ui.py (before main())**

```python
# ── Image downloader ───────────────────────────────────────────────────────────

IMG_SELECTORS = [
    ".question-and-submission-view img",
    ".question-component img",
    "[class*='TileMultipleChoices'] img",
    "[class*='SelectableTile']:not([class*='nonInteractive']) img",
    "[class*='stimulus'] img",
    "[class*='Stimulus'] img",
    "[class*='picture'] img",
]


def download_images(page, img_dir, session):
    """Download all question images. Returns list of local filenames."""
    paths = []
    seen  = set()

    for sel in IMG_SELECTORS:
        for img in page.query_selector_all(sel):
            src = img.get_attribute("src") or ""
            alt = clean(img.get_attribute("alt") or "")
            if not src or src in seen or src.startswith("data:") or alt in SKIP_ALTS:
                continue
            seen.add(src)

            full_url = src if src.startswith("http") else f"{BASE_URL}{src}"
            fname    = hashlib.md5(full_url.encode()).hexdigest()[:16] + ".jpg"
            fpath    = img_dir / fname

            if fpath.exists():
                paths.append(fname)
                continue

            try:
                resp = session.get(full_url, timeout=10)
                resp.raise_for_status()
                ct = resp.headers.get("content-type", "")
                if "png" in ct:
                    fname = fname.replace(".jpg", ".png")
                    fpath = img_dir / fname
                elif "webp" in ct:
                    fname = fname.replace(".jpg", ".webp")
                    fpath = img_dir / fname
                fpath.write_bytes(resp.content)
                paths.append(fname)
            except Exception:
                pass

    return paths
```

- [ ] **Step 2: Add scrape_skill() to ixl_scraper_ui.py (before main())**

```python
# ── Skill scraper ──────────────────────────────────────────────────────────────

def scrape_skill(page, skill, subject, year, max_questions, img_dir):
    """
    Scrape one skill. Returns (questions_list, skipped_count).
    Repeat-detection: stop when the same stem prefix appears twice.
    If max_questions > 0, also stop at that hard cap.
    """
    name = skill["name"]
    url  = skill["url"]
    session = requests.Session()

    try:
        page.goto(url, wait_until="domcontentloaded", timeout=20000)
        time.sleep(1.5)
    except PWTimeout:
        print(f"  Timeout loading skill.", flush=True)
        return [], 0

    html = page.content()
    qtype = detect_type(html)

    if should_skip(qtype):
        p_skip(qtype, name)
        return [], 1

    try:
        page.wait_for_selector(".question-component", timeout=8000)
    except PWTimeout:
        print(f"  No question found.", flush=True)
        return [], 0

    # Wait for first real question
    deadline = time.time() + 10
    while time.time() < deadline:
        if get_question_text(page) and len(get_question_text(page)) > 20:
            break
        time.sleep(0.5)

    results    = []
    seen_stems = {}   # stem_prefix -> count
    skipped    = 0
    prev_text  = ""

    while True:
        if max_questions > 0 and len(results) >= max_questions:
            break

        current_text = get_question_text(page)
        if not current_text or len(current_text) < 20 or current_text.startswith("Submit"):
            break

        # Re-detect type per question (IXL sometimes mixes types within a skill)
        html  = page.content()
        qtype = detect_type(html)

        if should_skip(qtype):
            p_skip(qtype, name)
            skipped += 1
            prev_text = current_text
            capture_answer(page, qtype)
            if not wait_for_new_question(page, prev_text):
                break
            continue

        stem_prefix = current_text[:80]
        seen_stems[stem_prefix] = seen_stems.get(stem_prefix, 0) + 1
        if seen_stems[stem_prefix] >= 2:
            break  # pool exhausted — seen this stem before

        # Extract question
        qc       = page.query_selector(".question-component")
        full     = clean(qc.inner_text() if qc else "")
        choices  = extract_choices(page, qtype)
        stem     = full
        if choices:
            idx = full.find(choices[0])
            if idx > 0:
                stem = full[:idx].strip()

        blanks = []
        if "fill" in qtype:
            inputs = page.query_selector_all("input[type='text'], input[type='number']")
            blanks = [clean(i.get_attribute("placeholder") or "") for i in inputs]

        # Images
        img_paths = download_images(page, img_dir, session)

        # Answer
        correct = capture_answer(page, qtype)

        q_index = len(results) + 1
        p_question(q_index, qtype)

        results.append({
            "question_id":    make_question_id(subject, year, name, q_index),
            "subject":        subject,
            "year":           year,
            "skill_name":     name,
            "skill_url":      url,
            "question_index": q_index,
            "format":         qtype,
            "question_text":  stem[:4000],
            "options":        choices,
            "correct_answer": correct,
            "blank_count":    len(blanks),
            "has_image":      bool(img_paths),
            "image_paths":    img_paths,
            "scraped_at":     datetime.now(timezone.utc).isoformat(),
            "quiz_ready":     bool(correct),
        })

        prev_text = current_text
        if not wait_for_new_question(page, prev_text):
            break

    return results, skipped
```

- [ ] **Step 3: End-to-end manual test against one skill**

```bash
python3 ixl_scraper_ui.py \
  --subject maths --year year-12 \
  --username supersheldon1 --password "3ej#A!@QH%f6" \
  --max-questions 3 \
  --output-dir output/maths/year-12 \
  --headless
```

Expected output:
```
Logging in as supersheldon1 ...
Login OK
Loading skill index: https://uk.ixl.com/maths/year-12
Found 290 skills.
[START] subject=maths year=year-12 total_skills=290
[SKILL] 1/290 Solve linear equations
[QUESTION] q=1 format=fill-in-blank
[QUESTION] q=2 format=fill-in-blank
[QUESTION] q=3 format=fill-in-blank
[SKILL_DONE] questions=3
...
```

Verify `output/maths/year-12/questions.json` exists and contains valid JSON with `correct_answer` populated.

- [ ] **Step 4: Commit**

```bash
git add ixl_scraper_ui.py
git commit -m "feat: complete unified scraper with image download and repeat detection"
```

---

## Task 11: End-to-end integration test via the dashboard

**Files:** No code changes — manual walkthrough.

- [ ] **Step 1: Start the Flask app**

```bash
python3 app.py
```

Open `http://localhost:5000` in browser.

- [ ] **Step 2: Run a small scrape via the UI**

1. In **Configure & Launch** tab: select `maths`, `year-12`, enter credentials, set max questions to `5`, leave headless checked.
2. Click **Run Scraper** — button should disable, status shows "Running: maths year-12".
3. UI switches to **Live Progress** tab automatically.
4. Verify: log lines appear in real time, stat cards update after each skill.
5. Wait for `[DONE]` line to appear in green.

- [ ] **Step 3: Review the scraped data**

1. Switch to **Review Data** tab.
2. Select `maths / year-12` from the dropdown.
3. Verify: question rows appear with skill name, format badge, question text, answer.
4. Type a search term — verify filtering works.
5. Click **Export CSV** — verify file downloads with correct headers.

- [ ] **Step 4: Test error path**

1. Enter a wrong password, click **Run Scraper**.
2. In Progress tab, verify `[ERROR] Login failed` appears in red.
3. Verify Run button re-enables after error.

- [ ] **Step 5: Final commit**

```bash
git add .
git commit -m "feat: IXL Scraper UI Dashboard — complete"
```

---

## Running All Tests

```bash
pytest tests/ -v
```

Expected: all unit and route tests pass (scraper browser tests are manual per Tasks 8–11).
