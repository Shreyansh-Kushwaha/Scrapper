from flask import Flask, Response, request, jsonify, render_template, stream_with_context
import json, subprocess, threading, queue, time, os
from pathlib import Path

app = Flask(__name__)
OUTPUT_BASE = Path(os.environ.get('IXL_OUTPUT_DIR', 'output'))

_procs      = []   # list of active Popen objects
_running    = False
_run_config = {}   # subject, year, output_dir, n_workers, total_skills, start_time
_lock       = threading.Lock()


# ── Helpers ────────────────────────────────────────────────────────────────────

def _merge_outputs(output_dir, n_workers):
    """Merge worker_{n}/questions.json files into questions.json. Returns count."""
    output_dir = Path(output_dir)
    all_q = []
    for w in range(n_workers):
        wfile = output_dir / f'worker_{w}' / 'questions.json'
        if wfile.exists():
            try:
                all_q.extend(json.loads(wfile.read_text(encoding='utf-8')))
            except Exception:
                pass
    all_q.sort(key=lambda q: (q.get('skill_name', ''), q.get('question_index', 0)))
    (output_dir / 'questions.json').write_text(
        json.dumps(all_q, indent=2, ensure_ascii=False), encoding='utf-8'
    )
    for w in range(n_workers):
        bfile = output_dir / f'_batch_{w}.json'
        if bfile.exists():
            bfile.unlink()
    return len(all_q)


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/discover', methods=['POST'])
def discover():
    if _running:
        return jsonify({'error': 'A scrape is already running'}), 409
    data = request.get_json()
    if not data.get('username') or not data.get('password'):
        return jsonify({'error': 'username and password required'}), 400

    VALID_SUBJECTS = {'maths', 'english', 'science'}
    VALID_YEARS    = {
        'reception', 'year-1', 'year-2', 'year-3', 'year-4', 'year-5',
        'year-6', 'year-7', 'year-8', 'year-9', 'year-10', 'year-11',
        'year-12', 'year-13',
    }
    if data.get('subject') not in VALID_SUBJECTS or data.get('year') not in VALID_YEARS:
        return jsonify({'error': 'invalid subject or year'}), 400

    cmd = [
        'python3', 'ixl_scraper_ui.py',
        '--subject',  data['subject'],
        '--year',     data['year'],
        '--username', data['username'],
        '--password', data['password'],
        '--discover-only', '--headless',
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
        for line in result.stdout.splitlines():
            if line.startswith('[SKILLS]'):
                skills = json.loads(line[8:].strip())
                return jsonify({'skills': skills})
        return jsonify({
            'error': 'Discovery failed — check credentials',
            'detail': (result.stdout + result.stderr)[-500:]
        }), 500
    except subprocess.TimeoutExpired:
        return jsonify({'error': 'Discovery timed out (90s)'}), 504


@app.route('/run', methods=['POST'])
def run():
    global _procs, _running, _run_config
    with _lock:
        if _running:
            return jsonify({'error': 'already running'}), 409

        data             = request.get_json()
        subject          = data['subject']
        year             = data['year']
        username         = data['username']
        password         = data['password']
        max_q            = str(data.get('max_questions', 0))
        headless         = data.get('headless', True)
        selected_skills  = data.get('selected_skills', [])
        workers          = max(1, min(5, int(data.get('workers', 1))))

        VALID_SUBJECTS = {'maths', 'english', 'science'}
        VALID_YEARS    = {
            'reception', 'year-1', 'year-2', 'year-3', 'year-4', 'year-5',
            'year-6', 'year-7', 'year-8', 'year-9', 'year-10', 'year-11',
            'year-12', 'year-13',
        }
        if subject not in VALID_SUBJECTS or year not in VALID_YEARS:
            return jsonify({'error': 'invalid subject or year'}), 400

        output_dir = OUTPUT_BASE / subject / year
        output_dir.mkdir(parents=True, exist_ok=True)

        if selected_skills:
            # Split into N batches (round-robin)
            batches = [[] for _ in range(workers)]
            for i, skill in enumerate(selected_skills):
                batches[i % workers].append(skill)

            _procs = []
            actual_workers = 0
            non_empty_batches = [(w_id, batch) for w_id, batch in enumerate(batches) if batch]
            for launch_idx, (w_id, batch) in enumerate(non_empty_batches):
                batch_file = output_dir / f'_batch_{w_id}.json'
                batch_file.write_text(json.dumps(batch), encoding='utf-8')

                worker_dir = output_dir / f'worker_{w_id}'
                worker_dir.mkdir(exist_ok=True)

                cmd = [
                    'python3', 'ixl_scraper_ui.py',
                    '--subject', subject, '--year', year,
                    '--username', username, '--password', password,
                    '--max-questions', max_q,
                    '--output-dir', str(worker_dir),
                    '--skills-file', str(batch_file),
                ]
                if headless:
                    cmd.append('--headless')
                _procs.append(subprocess.Popen(
                    cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, bufsize=1
                ))
                actual_workers += 1
                if launch_idx < len(non_empty_batches) - 1:
                    time.sleep(8)  # stagger startup — prevents simultaneous Chrome crashes
        else:
            # Original behaviour — single process, discovers skills itself
            cmd = [
                'python3', 'ixl_scraper_ui.py',
                '--subject', subject, '--year', year,
                '--username', username, '--password', password,
                '--max-questions', max_q,
                '--output-dir', str(output_dir / 'worker_0'),
            ]
            if headless:
                cmd.append('--headless')
            (output_dir / 'worker_0').mkdir(exist_ok=True)
            _procs = [subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1
            )]
            actual_workers = 1

        _run_config = {
            'subject':      subject,
            'year':         year,
            'output_dir':   str(output_dir),
            'n_workers':    actual_workers,
            'total_skills': len(selected_skills),
            'start_time':   time.time(),
        }
        _running = True
        return jsonify({'status': 'started', 'workers': actual_workers})


@app.route('/stop', methods=['POST'])
def stop():
    global _procs, _running
    for p in _procs:
        try:
            p.kill()
        except Exception:
            pass
    _procs = []
    with _lock:
        _running = False
    return jsonify({'status': 'stopped'})


@app.route('/stream')
def stream():
    def generate():
        global _procs, _running, _run_config
        if not _procs:
            yield 'data: [ERROR] No scraper running\n\n'
            return

        cfg  = dict(_run_config)
        n    = cfg['n_workers']
        total = cfg['total_skills']
        subj  = cfg['subject']
        yr    = cfg['year']

        # Emit a single [START] with the true total (workers emit their own subset counts).
        # In auto-discover mode (total=0) we let the scraper's own [START] pass through.
        server_emitted_start = bool(total)
        if total:
            yield f'data: [START] subject={subj} year={yr} total_skills={total}\n\n'

        msg_q = queue.Queue()
        total_skipped = 0

        def read_proc(proc, wid):
            try:
                for line in proc.stdout:
                    msg_q.put(('line', wid, line.rstrip()))
            finally:
                msg_q.put(('done', wid, proc.wait()))

        for i, p in enumerate(_procs):
            threading.Thread(target=read_proc, args=(p, i), daemon=True).start()

        try:
            done_count = 0
            while done_count < n:
                try:
                    kind, wid, val = msg_q.get(timeout=300)
                except queue.Empty:
                    yield 'data: [ERROR] stream timeout — no output for 5 minutes\n\n'
                    break

                if kind == 'done':
                    if val != 0:
                        yield f'data: [ERROR] worker {wid + 1} exited with code {val}\n\n'
                    done_count += 1
                else:
                    line = val
                    # In auto-discover mode pass the scraper's [START] through so the
                    # client can populate the total-skills counter.
                    if line.startswith('[START]'):
                        if not server_emitted_start:
                            yield f'data: {line}\n\n'
                        continue
                    # Filter per-worker [DONE] — we emit our own merged version below.
                    if line.startswith('[DONE]'):
                        continue
                    if line.startswith('[SKIP]'):
                        total_skipped += 1
                    prefix = f'[W{wid + 1}] ' if n > 1 else ''
                    yield f'data: {prefix}{line}\n\n'

            # Merge all worker outputs
            try:
                merged = _merge_outputs(cfg['output_dir'], n)
                elapsed = int(time.time() - cfg['start_time'])
                yield f'data: [DONE] total_questions={merged} elapsed={elapsed}s skipped={total_skipped}\n\n'
            except Exception as e:
                yield f'data: [ERROR] Merge failed: {e}\n\n'
        finally:
            with _lock:
                _running = False

    return Response(stream_with_context(generate()), mimetype='text/event-stream',
                    headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})


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


if __name__ == '__main__':
    app.run(debug=True, port=5000, threaded=True)
