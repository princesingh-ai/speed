'use strict';
const $ = id => document.getElementById(id);
let token = '', taskId = '', socket = null, events = [], snapshot = null;
let sequence = 0, generation = 0, retry = null, frame = null, refreshPending = false, refreshAgain = false;
const colors = ['#9faabd', '#79cfa9', '#92aff0', '#c5a0e8', '#e5b676', '#71c4d0', '#df96af'];
const terminal = new Set(['completed', 'failed', 'cancelled']);
function connection(text, live = false) { $('connection').textContent = text; $('connection').className = live ? 'live' : ''; }
function error(message = '') { $('error').textContent = message; }
async function api(path, options = {}) {
  const response = await fetch(path, {...options, headers: {'Content-Type': 'application/json', Authorization: `Bearer ${token}`, ...options.headers}});
  if (!response.ok) {
    if (response.status === 401) throw new Error('Session expired. Sign in again to reconnect.');
    throw new Error(`Request failed (${response.status}). Check access, task capacity and input.`);
  }
  return response;
}
function jsonPost(body = {}) { return {method: 'POST', body: JSON.stringify(body)}; }
$('login-form').addEventListener('submit', async event => {
  event.preventDefault(); error();
  const button = event.submitter; button.disabled = true;
  try {
    const response = await fetch('/api/v1/auth/login', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({username: $('username').value, password: $('password').value})});
    if (!response.ok) throw new Error('Sign-in failed. Check your workspace credentials.');
    token = (await response.json()).access_token;
    $('password').value = ''; $('identity').hidden = false;
    $('identity').textContent = `Signed in as ${$('username').value}`;
    $('start').disabled = false;
    const saved = location.hash.slice(1);
    if (/^task_[a-f0-9]+$/.test(saved)) await selectTask(saved);
  } catch (e) { error(e.message); } finally { button.disabled = false; }
});
$('task-form').addEventListener('submit', async event => {
  event.preventDefault(); error(); $('start').disabled = true;
  try {
    const result = await (await api('/api/v1/agent/tasks', jsonPost({objective: $('objective').value, flow: $('flow').value, input_path: $('input-path').value}))).json();
    await selectTask(result.task_id);
  } catch (e) { error(e.message); } finally { $('start').disabled = !token; }
});
async function selectTask(id) {
  generation++; clearTimeout(retry); if (socket) socket.close();
  taskId = id; location.hash = id; events = []; sequence = 0; snapshot = null;
  $('notice').textContent = ''; $('reconnect').disabled = false;
  scheduleRender(); await connect(generation);
}
async function connect(epoch) {
  if (epoch !== generation) return;
  connection('Connecting…');
  try {
    const result = await (await api(`/api/v1/agent/tasks/${taskId}/ticket`, jsonPost())).json();
    if (epoch !== generation) return;
    const ws = new WebSocket(`${location.protocol === 'https:' ? 'wss:' : 'ws:'}//${location.host}/api/v1/agent/tasks/${taskId}/events`);
    socket = ws;
    ws.onopen = () => ws.send(JSON.stringify({ticket: result.ticket, after_sequence: sequence}));
    ws.onmessage = message => {
      if (epoch !== generation) return;
      const data = JSON.parse(message.data);
      if (data.type === 'snapshot') {
        snapshot = data.snapshot;
        if (data.history_truncated) { events = []; $('notice').textContent = 'Earlier history has expired. Showing retained events and current state.'; }
        for (const event of data.events) accept(event);
        connection('Live', true); renderSnapshot(); scheduleRender();
      } else if (data.type === 'event') {
        accept(data.event); scheduleRender();
        if (/^(step\.|task\.|artifact\.|plan\.|review\.)/.test(data.event.event_type)) refreshSnapshot(epoch);
      }
    };
    ws.onclose = event => {
      if (epoch !== generation) return;
      connection('Disconnected');
      if ([4400, 4401].includes(event.code)) { error('Connection authorization failed. Sign in and reconnect.'); return; }
      if (!snapshot || !terminal.has(snapshot.status)) {
        connection('Reconnecting…'); retry = setTimeout(() => connect(epoch), 1500);
      }
    };
    ws.onerror = () => connection('Connection interrupted');
  } catch (e) { connection('Disconnected'); error(e.message); }
}
function accept(event) {
  if (event.sequence <= sequence) return;
  if (sequence && event.sequence !== sequence + 1) $('notice').textContent = 'History gap detected. Reconnect to replay retained events.';
  sequence = event.sequence; events.push(event);
  if (events.length > 2000) events.shift();
}
async function refreshSnapshot(epoch) {
  if (refreshPending) { refreshAgain = true; return; }
  refreshPending = true;
  try {
    const data = await (await api(`/api/v1/agent/tasks/${taskId}`)).json();
    if (epoch === generation) { snapshot = data; renderSnapshot(); scheduleRender(); }
  } catch (e) { error(e.message); } finally {
    refreshPending = false;
    if (refreshAgain) { refreshAgain = false; refreshSnapshot(generation); }
  }
}
function renderSnapshot() {
  if (!snapshot) return;
  $('task-title').textContent = snapshot.objective; $('task-id').textContent = snapshot.task_id;
  $('status').textContent = snapshot.status; $('status').className = `pill ${snapshot.status}`;
  $('planner').textContent = `Planner: ${snapshot.planner_mode === 'deterministic_fallback' ? 'Deterministic fallback' : snapshot.planner_mode === 'local_model' ? 'Local AI' : 'planning'}`;
  $('progress').textContent = `${snapshot.steps.filter(s => s.status === 'completed').length} / ${snapshot.steps.length} steps`;
  $('result').textContent = snapshot.summary || (terminal.has(snapshot.status) ? `Task ${snapshot.status}.` : 'Receiving backend execution events.');
  $('artifacts').replaceChildren();
  for (const artifact of snapshot.artifacts) {
    const button = document.createElement('button'); button.textContent = `↓ ${artifact.name}`;
    button.onclick = async () => {
      button.disabled = true;
      try {
        const response = await api(artifact.download_url);
        const url = URL.createObjectURL(await response.blob());
        const link = document.createElement('a'); link.href = url; link.download = artifact.name; link.click();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
      } catch (e) { error(e.message); } finally { button.disabled = false; }
    };
    $('artifacts').append(button);
  }
  if (!snapshot.artifacts.length) $('artifacts').textContent = 'No artifacts yet.';
  renderReview();
  $('approvals').replaceChildren();
  for (const step of snapshot.steps.filter(s => s.status === 'waiting')) {
    const event = [...events].reverse().find(e => e.step_id === step.id && e.event_type === 'step.waiting');
    if (!event) continue;
    const box = document.createElement('div');
    const text = document.createElement('div'); text.textContent = `Approve ${event.metadata.permission} · ${event.metadata.resource}`; box.append(text);
    for (const action of ['approve', 'deny']) {
      const button = document.createElement('button'); button.textContent = action === 'approve' ? 'Approve once' : 'Deny';
      button.onclick = async () => {
        box.querySelectorAll('button').forEach(b => b.disabled = true);
        try { await api(`/api/v1/permissions/${event.metadata.consent_id}/${action}`, jsonPost()); await refreshSnapshot(generation); }
        catch (e) { error(e.message); box.querySelectorAll('button').forEach(b => b.disabled = false); }
      };
      box.append(button);
    }
    $('approvals').append(box);
  }
}
function scheduleRender() { if (!frame) frame = requestAnimationFrame(() => { frame = null; render(); }); }
function svg(tag, attrs) {
  const node = document.createElementNS('http://www.w3.org/2000/svg', tag);
  for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, value);
  return node;
}
function render() {
  $('empty').hidden = events.length > 0;
  const lanes = $('lanes'), rows = $('rows'); lanes.replaceChildren(); rows.replaceChildren();
  const width = Math.max(85, (Math.max(0, ...events.map(e => e.lane_id)) + 1) * 18 + 24);
  lanes.setAttribute('width', width); lanes.setAttribute('height', events.length * 70);
  $('history').style.minWidth = `${width + 440}px`;
  const previous = new Map(), completed = new Map();
  const running = new Set((snapshot?.steps || []).filter(s => s.status === 'running').map(s => s.id));
  const lastByStep = new Map(); events.forEach(e => { if (e.step_id) lastByStep.set(e.step_id, e.sequence); });
  const path = (from, to, color) => lanes.append(svg('path', {d: `M ${from.x} ${from.y} C ${from.x} ${from.y + 24}, ${to.x} ${to.y - 24}, ${to.x} ${to.y}`, stroke: color, 'stroke-width': 1.6, fill: 'none', opacity: .8}));
  events.forEach((event, index) => {
    const point = {x: 16 + event.lane_id * 18, y: index * 70 + 35};
    const color = colors[event.lane_id % colors.length];
    if (previous.has(event.lane_id)) path(previous.get(event.lane_id), point, color);
    if (event.event_type === 'step.started') {
      const deps = event.metadata.dependencies || [];
      for (const dep of deps) if (completed.has(dep)) path(completed.get(dep), point, color);
      if (!deps.length && previous.has(0)) path(previous.get(0), point, color);
    }
    if (event.event_type === 'step.completed') completed.set(event.step_id, point);
    previous.set(event.lane_id, point);
    const current = running.has(event.step_id) && lastByStep.get(event.step_id) === event.sequence;
    lanes.append(svg('circle', {cx: point.x, cy: point.y, r: current ? 5 : 3.5, fill: event.status === 'failed' ? '#ef9b89' : color, class: current ? 'pulse' : ''}));
    const row = document.createElement('li'); row.style.paddingLeft = `${width + 8}px`;
    if (current) row.classList.add('current');
    if ($('filter').value !== 'all' && !event.event_type.startsWith(`${$('filter').value}.`)) row.classList.add('dim');
    const copy = document.createElement('div'); copy.className = 'event-copy';
    const title = document.createElement('div'); title.className = 'event-title'; title.textContent = event.title; title.title = event.title;
    const meta = document.createElement('div'); meta.className = 'event-meta';
    meta.textContent = `#${event.sequence} · ${event.event_type}${event.duration_ms != null ? ` · ${event.duration_ms} ms` : ''}${event.summary ? ` · ${event.summary}` : ''}`;
    copy.append(title, meta);
    const state = document.createElement('span'); state.className = `pill ${event.status}`; state.textContent = event.status;
    const detail = document.createElement('details'), summary = document.createElement('summary'), pre = document.createElement('pre');
    summary.textContent = 'Details'; pre.textContent = JSON.stringify({step: event.step_id, timestamp: event.timestamp, ...event.metadata}, null, 2);
    detail.append(summary, pre); row.append(copy, state, detail); rows.append(row);
  });
  if ($('follow').checked) $('history-viewport').scrollTop = $('history-viewport').scrollHeight;
}
$('filter').onchange = scheduleRender;

function renderReview() {
  const box = $('review'), review = snapshot.review;
  box.hidden = !review;
  if (!review) { box.replaceChildren(); return; }
  // Preserve a note being typed while another event refreshes the snapshot.
  if (box.dataset.task === taskId && box.dataset.status === review.status) return;
  box.dataset.task = taskId; box.dataset.status = review.status; box.replaceChildren();
  const labels = {pending: 'Review required', approved: 'Approved', changes_requested: 'Changes requested', rejected: 'Rejected'};
  const heading = document.createElement('h3');
  heading.textContent = labels[review.status] + (review.reviewer_name ? ` by ${review.reviewer_name}` : '');
  box.append(heading);
  if (review.status !== 'pending') {
    const note = document.createElement('p'); note.textContent = review.comment; box.append(note); return;
  }
  const label = document.createElement('label'), note = document.createElement('textarea');
  label.textContent = 'Review note (optional)'; note.maxLength = 2000; label.append(note); box.append(label);
  for (const decision of ['approved', 'changes_requested', 'rejected']) {
    const button = document.createElement('button');
    button.textContent = {approved: 'Approve', changes_requested: 'Request changes', rejected: 'Reject'}[decision];
    button.onclick = async () => {
      const epoch = generation, id = taskId;
      box.querySelectorAll('button').forEach(b => b.disabled = true);
      try {
        const result = await (await api(`/api/v1/agent/tasks/${id}/review`, jsonPost({decision, comment: note.value}))).json();
        if (epoch === generation) { snapshot = result; renderSnapshot(); }
      } catch (e) {
        if (epoch === generation) { error(e.message); box.querySelectorAll('button').forEach(b => b.disabled = false); }
      }
    };
    box.append(button);
  }
}
$('reconnect').onclick = () => { generation++; clearTimeout(retry); if (socket) socket.close(); connect(generation); };
