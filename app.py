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
