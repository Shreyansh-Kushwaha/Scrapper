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
