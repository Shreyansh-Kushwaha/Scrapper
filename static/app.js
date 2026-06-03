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
