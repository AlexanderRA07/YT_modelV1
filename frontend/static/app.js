// ============================================================
// app.js — Shared frontend logic
// WebSocket client, API helpers, toast notifications,
// and UI utilities used across all pages.
// ============================================================


// ── WebSocket ────────────────────────────────────────────────
const WS_URL = `ws://${location.host}/ws`;
let socket = null;
let _messageHandlers = [];

function connectWS() {
  socket = new WebSocket(WS_URL);

  socket.addEventListener('open', () => {
    setStatusDot('connected');
    console.log('[WS] Connected');
  });

  socket.addEventListener('message', (event) => {
    let msg;
    try { msg = JSON.parse(event.data); }
    catch { return; }
    _messageHandlers.forEach(fn => fn(msg));
  });

  socket.addEventListener('close', () => {
    setStatusDot('disconnected');
    console.log('[WS] Disconnected. Reconnecting in 3s...');
    setTimeout(connectWS, 3000);
  });

  socket.addEventListener('error', () => {
    setStatusDot('error');
  });
}

function onMessage(handler) {
  _messageHandlers.push(handler);
}

function setStatusDot(state) {
  const dot = document.getElementById('status-dot');
  const label = document.getElementById('status-label');
  if (!dot) return;
  dot.className = 'status-dot';
  if (state === 'connected')    { dot.classList.add('connected'); if (label) label.textContent = 'connected'; }
  else if (state === 'error')   { dot.classList.add('error');     if (label) label.textContent = 'error'; }
  else                          {                                  if (label) label.textContent = 'offline'; }
}


// ── API helpers ──────────────────────────────────────────────
const API = {
  async get(path) {
    const r = await fetch(path);
    if (!r.ok) throw new Error(`GET ${path} → ${r.status}`);
    return r.json();
  },

  async post(path, body = {}) {
    const r = await fetch(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    });
    if (!r.ok) {
      const err = await r.text();
      throw new Error(`POST ${path} → ${r.status}: ${err}`);
    }
    return r.json();
  },

  async delete(path) {
    const r = await fetch(path, { method: 'DELETE' });
    if (!r.ok) throw new Error(`DELETE ${path} → ${r.status}`);
    return r.json();
  }
};


// ── Toast notifications ──────────────────────────────────────
function toast(message, type = 'info', duration = 4000) {
  const container = document.getElementById('toast-container');
  if (!container) return;

  const icons = { ok: '✓', warn: '⚠', error: '✕', info: '·' };
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  el.innerHTML = `<span>${icons[type] || icons.info}</span><span>${message}</span>`;
  container.appendChild(el);

  setTimeout(() => {
    el.style.opacity = '0';
    el.style.transition = 'opacity 0.3s';
    setTimeout(() => el.remove(), 300);
  }, duration);
}


// ── Project/channel context ──────────────────────────────────
// Stored in sessionStorage so it survives navigation within a session
const CTX = {
  set(channel, projectId) {
    sessionStorage.setItem('channel', channel);
    sessionStorage.setItem('project_id', projectId);
  },
  get() {
    return {
      channel:   sessionStorage.getItem('channel'),
      projectId: sessionStorage.getItem('project_id')
    };
  },
  clear() {
    sessionStorage.removeItem('channel');
    sessionStorage.removeItem('project_id');
  }
};


// ── Asset helpers ────────────────────────────────────────────
const STATE_LABELS = {
  pending:   'Pending',
  review:    'Review',
  approved:  'Approved',
  rejected:  'Rejected',
  error:     'Error',
  frozen:    'Frozen',
  waiting:   'Waiting',
  animating: 'Animating',
  thumbnail: 'Thumbnail',
  done:      'Done'
};

const TYPE_LABELS = {
  image:     'Image',
  animation: 'Animation',
  voice:     'Voice',
  music:     'Music',
  thumbnail: 'Thumbnail'
};

function stateBadge(state) {
  const label = STATE_LABELS[state] || state;
  return `<span class="state-badge state-${state}">${label}</span>`;
}

function assetFileUrl(channel, projectId, filename) {
  return `/api/projects/${channel}/${projectId}/assets/file/${filename}`;
}


// ── Routing helpers ──────────────────────────────────────────
function goto(path) { window.location.href = path; }


// ── Format info ──────────────────────────────────────────────
const FORMAT_INFO = {
  '1min':  { label: '1 min',  note: '~150 words · 3 images' },
  '2min':  { label: '2 min',  note: '~300 words · 5 images' },
  '10min': { label: '10 min', note: '~1400 words · 15 images' },
  '15min': { label: '15 min', note: '~2000 words · 23 images' }
};


// ── Init ─────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  connectWS();
});
