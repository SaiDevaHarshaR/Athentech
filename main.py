<!DOCTYPE html>
<html lang="en">
<head>
  <link rel="icon" href="Favicon.ico" type="image/x-icon" />
<link rel="apple-touch-icon" href="Favicon.ico" />
<meta charset="UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1.0" />
<title>Sahasra AI Assistant</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }

    body {
    font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
    background: #ffffff;
    height: 100vh;
    display: flex;
    justify-content: center;
    align-items: center;
  }
  @keyframes bg-drift {
    0%, 100% { background-position: 0% 50%; }
    50% { background-position: 100% 50%; }
  }
  .typing-dots span {
  display: inline-block;
  width: 6px; height: 6px;
  margin: 0 2px;
  background: #999;
  border-radius: 50%;
  animation: typing-bounce 1.2s infinite ease-in-out;
}
.typing-dots span:nth-child(2) { animation-delay: 0.2s; }
.typing-dots span:nth-child(3) { animation-delay: 0.4s; }
@keyframes typing-bounce {
  0%, 60%, 100% { transform: translateY(0); opacity: 0.4; }
  30% { transform: translateY(-4px); opacity: 1; }
}

  .container {
    width: 100%;
    height: 100vh;
    background: linear-gradient(135deg, #f0f4ff 0%, #fdf2ff 50%, #f0fdfa 100%);
    background-size: 200% 200%;
    animation: bg-drift 18s ease-in-out infinite;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }

  /* Header */
  .header {
    background: linear-gradient(135deg, #8B008B, #4c1d95, #1e293b);
    background-size: 200% 200%;
    animation: header-shift 8s ease-in-out infinite;
    color: white;
    padding: 16px 18px;
    display: flex;
    align-items: center;
    gap: 12px;
    box-shadow: 0 4px 20px rgba(139,0,139,0.25);
    position: relative;
    z-index: 2;
  }
  @keyframes header-shift {
    0%, 100% { background-position: 0% 50%; }
    50% { background-position: 100% 50%; }
  }

  .logo {
    width: 40px;
    height: 40px;
    background: transparent;
    border-radius: 10px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-weight: 700;
    font-size: 14px;
  }

  .header-info { flex: 1; }
  .header-info h1 { font-size: 15px; font-weight: 600; }
  .header-info p { font-size: 12px; opacity: 0.7; margin-top: 2px; }

  .badge {
    font-size: 11px;
    padding: 4px 10px;
    border-radius: 20px;
    font-weight: 600;
    background: #22c55e;
    color: white;
  }
  .badge.premium { background: #f59e0b; }

  /* Chat area */
  .chat {
    flex: 1;
    overflow-y: auto;
    padding: 16px 14px;
    display: flex;
    flex-direction: column;
    gap: 12px;
    background-image: radial-gradient(circle, #e8ecf3 1px, transparent 1px);
    background-size: 18px 18px;
    background-color: #fafbfd;
  }

  .message {
    max-width: 85%;
    padding: 11px 13px;
    border-radius: 14px;
    font-size: 14px;
    line-height: 1.5;
  }

  .bot {
    background: white;
    border: 1px solid #e2e8f0;
    align-self: flex-start;
    border-radius: 18px;
    border-bottom-left-radius: 4px;
    box-shadow: 0 2px 8px rgba(30,41,59,0.06);
  }

  .user {
    background: linear-gradient(135deg, #2563eb, #7c3aed);
    color: white;
    align-self: flex-end;
    border-radius: 18px;
    border-bottom-right-radius: 4px;
    box-shadow: 0 2px 10px rgba(124,58,237,0.25);
  }

  .time {
    font-size: 10px;
    opacity: 0.55;
    margin-top: 5px;
    display: block;
  }

  /* Role chip */
  .role-chip {
    display: inline-block;
    background: #fef3c7;
    color: #92400e;
    font-size: 11px;
    padding: 2px 8px;
    border-radius: 10px;
    margin-bottom: 6px;
    font-weight: 600;
  }
  .msg-enter {
  animation: msg-rise 0.45s cubic-bezier(0.34, 1.4, 0.4, 1) both;
}
@keyframes msg-rise {
  from { opacity: 0; transform: translateY(24px) scale(0.9); }
  60% { opacity: 1; }
  to { opacity: 1; transform: translateY(0) scale(1); }
}
  /* Suggestions */
.suggestions {
  padding: 0 14px;
  max-height: 0;
  overflow: hidden;
  opacity: 0;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  background: #e2e8f0;
  transition: max-height 0.25s ease, opacity 0.2s ease, padding 0.25s ease;
}

.suggestions.open {
  padding: 10px 14px;
  max-height: 200px;
  opacity: 1;
}

.suggestions button {
  background: white;
  border: 1px solid #cbd5e1;
  color: #1e293b;
  padding: 7px 13px;
  border-radius: 20px;
  font-size: 12.5px;
  cursor: pointer;
  transform: scale(0.9);
  opacity: 0;
  animation: popIn 0.2s ease forwards;
  transition: background 0.15s, color 0.15s, border-color 0.15s, transform 0.1s;
}

.suggestions button:hover {
  background: #2563eb;
  color: white;
  border-color: #2563eb;
  transform: scale(1.05);
}
@keyframes popIn {
  to { transform: scale(1); opacity: 1; }
}

  /* Input */
  .input-area {
    padding: 12px 14px;
    background: white;
    border-top: 1px solid #e2e8f0;
    display: flex;
    gap: 10px;
  }

  .input-area input {
    flex: 1;
    border: 1px solid #cbd5e1;
    border-radius: 12px;
    padding: 12px 14px;
    font-size: 14px;
    outline: none;
  }

   .input-area input:focus {
    border-color: #2563eb;
    box-shadow: 0 0 0 3px rgba(37,99,235,0.12);
    transition: box-shadow 0.15s ease, border-color 0.15s ease;
  }

  .input-area button {
    background: linear-gradient(135deg, #2563eb, #7c3aed);
    color: white;
    border: none;
    width: 46px;
    border-radius: 12px;
    font-size: 18px;
    cursor: pointer;
    box-shadow: 0 2px 10px rgba(124,58,237,0.3);
    transition: transform 0.15s cubic-bezier(0.34,1.56,0.64,1), box-shadow 0.15s ease;
  }
  .input-area button:hover { transform: scale(1.08); box-shadow: 0 4px 16px rgba(124,58,237,0.4); }
  .input-area button:active { transform: scale(0.9); }
  .search-card {
  background: #f0f9ff;
  border: 1px solid #bae6fd;
  border-radius: 12px;
  padding: 16px;
  margin: 8px 0;
}
.search-card-stats { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 4px; }
.search-card-stat-pill {
  background: #e0f2fe; color: #0369a1; font-size: 10.5px;
  padding: 3px 8px; border-radius: 10px;
}
.search-card-header { font-weight: 700; font-size: 14px; color: #0c4a6e; }
.search-card-subtitle { font-size: 11px; color: #0369a1; margin-top: 2px; margin-bottom: 10px; }
.search-card-item {
  display: flex; justify-content: space-between;
  padding: 6px 0; border-bottom: 1px solid #e0f2fe; font-size: 12.5px;
}
.search-card-item:last-child { border-bottom: none; }
.search-card-item span { color: #64748b; }
.search-card-footer { margin-top: 10px; font-size: 10.5px; color: #64748b; font-style: italic; }

  /* ===== Dashboard Card ===== */
  .dash-card {
    max-width: 92%;
    align-self: flex-start;
    background: white;
    border: 1px solid #e2e8f0;
    border-radius: 14px;
    border-bottom-left-radius: 4px;
    box-shadow: 0 1px 2px rgba(0,0,0,0.04);
    padding: 14px 16px;
    font-size: 13px;
  }

  .dash-card-header {
    display: flex;
    align-items: baseline;
    gap: 7px;
    margin-bottom: 12px;
    font-size: 15px;
  }
  .dash-card-icon { font-size: 16px; }
  .dash-card-title { font-weight: 700; color: #0f766e; }
  .dash-card-subtitle { color: #64748b; font-size: 13px; }

  .dash-meta-line {
    display: flex;
    align-items: center;
    gap: 6px;
    color: #475569;
    font-size: 13px;
    margin-bottom: 4px;
  }

  .dash-stat-grid {
    display: flex;
    flex-wrap: wrap;
    gap: 10px;
    margin-bottom: 10px;
  }
  .dash-stat-box {
    background: #eff6ff;
    border-left: 3px solid #2563eb;
    border-radius: 6px;
    padding: 7px 12px;
    min-width: 90px;
    flex: 1 1 auto;
  }
  .dash-stat-label {
    font-size: 10px;
    font-weight: 700;
    color: #64748b;
    letter-spacing: 0.03em;
    text-transform: uppercase;
  }
  .dash-stat-value {
    font-size: 17px;
    font-weight: 700;
    color: #1e3a8a;
    margin-top: 1px;
  }

  .dash-divider {
    border: none;
    border-top: 1px dotted #cbd5e1;
    margin: 12px 0;
  }

  .dash-callout {
    font-size: 13px;
    margin-bottom: 4px;
  }
  .dash-callout-label { font-weight: 700; color: #0f766e; }
  .dash-delta-down { color: #dc2626; font-weight: 700; }
  .dash-delta-up { color: #16a34a; font-weight: 700; }

  .dash-bar-section-title {
    font-weight: 700;
    color: #0f766e;
    margin-bottom: 8px;
    font-size: 13px;
  }
  .status-dot {
  display: inline-block;
  width: 6px; height: 6px;
  border-radius: 50%;
  background: #4ade80;
  margin-right: 5px;
  vertical-align: middle;
  animation: status-pulse 2s ease-in-out infinite;
}
@keyframes status-pulse {
  0%, 100% { opacity: 1; box-shadow: 0 0 0 0 rgba(74,222,128,0.5); }
  50% { opacity: 0.7; box-shadow: 0 0 0 4px rgba(74,222,128,0); }
}
  .dash-bar-section-title .dash-subtitle-italic {
    font-weight: 400;
    font-style: italic;
    color: #64748b;
  }

  .dash-bar-row {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 6px;
    font-size: 12px;
  }
  .dash-bar-label {
    width: 96px;
    flex-shrink: 0;
    color: #334155;
    line-height: 1.25;
  }
  .dash-bar-track {
    flex: 1;
    height: 14px;
    background: repeating-linear-gradient(45deg, #f1f5f9, #f1f5f9 3px, #e2e8f0 3px, #e2e8f0 6px);
    border-radius: 3px;
    overflow: hidden;
    position: relative;
  }
  .dash-bar-fill {
    height: 100%;
    background: #1e293b;
    border-radius: 3px 0 0 3px;
  }
  .dash-bar-values {
    flex-shrink: 0;
    display: flex;
    gap: 10px;
    min-width: 70px;
    justify-content: flex-end;
    color: #334155;
    font-variant-numeric: tabular-nums;
  }

  .dash-footer {
    margin-top: 10px;
    font-weight: 700;
    color: #0f766e;
    font-size: 13px;
  }

  .dash-card-time {
    font-size: 10px;
    opacity: 0.55;
    margin-top: 8px;
    display: block;
    text-align: right;
  }

  /* ===== List Card (record lists: recent patients, top doctors, etc.) ===== */
  .dash-list-intro {
    color: #475569;
    font-size: 13px;
    margin-bottom: 10px;
  }

  .dash-list-item {
    display: flex;
    gap: 10px;
    padding: 8px 0;
    border-bottom: 1px solid #f1f5f9;
  }
  .dash-list-item:last-of-type { border-bottom: none; }

  .dash-list-badge {
    flex-shrink: 0;
    width: 20px;
    height: 20px;
    border-radius: 50%;
    background: #2563eb;
    color: white;
    font-size: 11px;
    font-weight: 700;
    display: flex;
    align-items: center;
    justify-content: center;
    margin-top: 1px;
  }

  .dash-list-body { flex: 1; min-width: 0; }
  .dash-list-primary {
    font-weight: 700;
    color: #1e293b;
    font-size: 13px;
  }
  .dash-list-fields {
    color: #64748b;
    font-size: 12px;
    margin-top: 1px;
  }
  .dash-list-fields span:not(:last-child)::after {
    content: " · ";
    color: #cbd5e1;
  }

  .dash-list-footer {
    margin-top: 10px;
    font-size: 12px;
    font-style: italic;
    color: #64748b;
  }
</style>
</head>
<body>
  <div class="container">
    <div class="header">
      <div class="logo"><img src="Favicon.ico" alt="AthenTech" style="width: 24px; height: 24px; border-radius: 4px;" /></div>
      <div class="header-info">
        <h1>Sahasra AI Assistant</h1>
        <p id="status"><span class="status-dot"></span>General Mode</p>
      </div>
      <div class="badge" id="modeBadge">Normal</div>
    </div>
<div id="usageBanner" style="display:none; background:#fef3c7; color:#92400e; padding:8px 14px; font-size:12px; justify-content:space-between; align-items:center;">
  <span id="usageBannerText"></span>
  <button onclick="document.getElementById('usageBanner').style.display='none'" style="background:none;border:none;cursor:pointer;font-size:14px;">×</button>
</div>
    <div class="chat" id="chat"></div>
    <div class="suggestions" id="suggestions"></div>

    <div class="input-area">
      <input id="msg" type="text" placeholder="Ask anything..." onkeydown="if(event.key==='Enter')handleSend()" />
      <button onclick="handleSend()">→</button>
        <button type="button" id="excelBtn" onclick="showExcelMenu()" style="display:none;">Excel ▾</button>
    </div>


  

    <div style="position:relative; display:flex; align-items:center; justify-content:center; padding:6px; font-size:10px; color:#94a3b8; background:white;">
      <span onclick="document.getElementById('disclaimerModal').style.display='flex'" style="position:absolute; left:10px; cursor:pointer; font-size:13px;" title="Disclaimer">⚠️</span>
      <span>Powered by AthenTech</span>
    </div>
  </div>

  <div id="disclaimerModal" style="display:none; position:fixed; inset:0; background:rgba(0,0,0,0.3); z-index:9999; align-items:center; justify-content:center;">
    <div style="background:white; width:300px; max-width:85%; border-radius:6px; box-shadow:0 8px 24px rgba(0,0,0,0.3); overflow:hidden;">
      <div style="display:flex; justify-content:space-between; align-items:center; background:#e2e8f0; padding:8px 12px; border-bottom:1px solid #cbd5e1;">
        <span style="font-size:12px; font-weight:700; color:#1e293b;">Disclaimer</span>
        <span onclick="document.getElementById('disclaimerModal').style.display='none'" style="cursor:pointer; width:20px; height:20px; display:flex; align-items:center; justify-content:center; background:#dc2626; color:white; font-size:12px; font-weight:700; border-radius:2px;">✕</span>
      </div>
      <div style="padding:16px; font-size:13px; line-height:1.5; color:#334155;">
        ⚠️ This assistant provides informational support only. It is not a substitute for professional medical advice. Patient data access is role-restricted and audited.
      </div>
    </div>
  </div>

<script>
const chatEl = document.getElementById('chat');
const suggestionsEl = document.getElementById('suggestions');
const statusEl = document.getElementById('status');
const modeBadge = document.getElementById('modeBadge');
const input = document.getElementById('msg');

const API_URL = "http://192.168.0.163:8000/ask";
function getDeviceFingerprint() {
  const raw = [
    navigator.userAgent,
    navigator.language,
    screen.width + 'x' + screen.height,
    screen.colorDepth,
    Intl.DateTimeFormat().resolvedOptions().timeZone,
  ].join('|');
  let hash = 0;
  for (let i = 0; i < raw.length; i++) {
    hash = ((hash << 5) - hash + raw.charCodeAt(i)) | 0;
  }
  return 'fp_' + Math.abs(hash).toString(36);
}
const DEVICE_FINGERPRINT = getDeviceFingerprint();
let state = {
  mode: 'normal',
  activationCode: null,
  role: null,
  waitingForCode: false,
  history: []
};

function now() {
  const d = new Date();
  let h = d.getHours(), m = d.getMinutes();
  const ap = h >= 12 ? 'PM' : 'AM';
  h = h % 12 || 12;
  return `${h}:${m < 10 ? '0' + m : m} ${ap}`;
}

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

function addMessage(text, type) {
  if (type === 'bot' && window.parent !== window) {
    const preview = (text || '').replace(/```[\s\S]*?```/g, '').replace(/[*_#]/g, '').trim().slice(0, 80);
    window.parent.postMessage({ type: 'sahasra-new-message', preview: preview || 'New message' }, '*');
  }

  const card = type === 'bot' ? extractDashboardCard(text) : null;
  if (card) {
    renderDashboardCard(card);
    return;
  }

  const listCard = type === 'bot' ? extractListCard(text) : null;
  if (listCard) {
    renderListCard(listCard);
    return;
  }

  const searchCard = type === 'bot' ? extractSearchCard(text) : null;
  if (searchCard) {
    renderSearchCard(searchCard);
    return;
  }

  const div = document.createElement('div');
  div.className = `message ${type}`;

  // Escape raw text FIRST — text can contain real data pulled from the
  // hospital DB (patient names, etc). Without escaping first, any HTML
  // characters in that data would render as live markup instead of
  // plain text — a real injection risk, not just a formatting bug.
  let formatted = escapeHtml(text)
    .replace(/\*\*(.*?)\*\*/g, '<b>$1</b>')
    .replace(/\*(.*?)\*/g, '<i>$1</i>')
    .replace(/\n/g, '<br>');

  div.innerHTML = `${formatted}<span class="time">${now()}</span>`;
  div.classList.add('msg-enter');
  chatEl.appendChild(div);
  chatEl.scrollTop = chatEl.scrollHeight;
  return div;
}
function extractDashboardCard(text) {
  // The LLM emits a ```dashboard-card fenced JSON block when a question
  // calls for a stat/breakdown summary. Anything else (a plain answer,
  // an explanation, a refusal) just falls through to normal text
  // rendering — this only activates for genuinely structured answers.
  const match = text.match(/```dashboard-card\s*([\s\S]*?)```/);
  if (!match) return null;
  try {
    const data = JSON.parse(match[1]);
    if (!data || !data.title || !Array.isArray(data.stats)) return null;
    return data;
  } catch (e) {
    return null; // malformed JSON — fall back to plain text rather than crash
  }
}

function renderDashboardCard(data) {
  const card = document.createElement('div');
  card.className = 'message bot dash-card';

  const header = document.createElement('div');
  header.className = 'dash-card-header';
  if (data.icon) {
    const icon = document.createElement('span');
    icon.className = 'dash-card-icon';
    icon.textContent = data.icon;
    header.appendChild(icon);
  }
  const title = document.createElement('span');
  title.className = 'dash-card-title';
  title.textContent = data.title;
  header.appendChild(title);
  if (data.subtitle) {
    const sub = document.createElement('span');
    sub.className = 'dash-card-subtitle';
    sub.textContent = ' · ' + data.subtitle;
    header.appendChild(sub);
  }
  card.appendChild(header);

  if (Array.isArray(data.meta)) {
    for (const m of data.meta) {
      const line = document.createElement('div');
      line.className = 'dash-meta-line';
      if (m.icon) {
        const icon = document.createElement('span');
        icon.textContent = m.icon;
        line.appendChild(icon);
      }
      line.appendChild(document.createTextNode(m.text || ''));
      card.appendChild(line);
    }
  }

  if (data.stats && data.stats.length) {
    const grid = document.createElement('div');
    grid.className = 'dash-stat-grid';
    for (const stat of data.stats) {
      const box = document.createElement('div');
      box.className = 'dash-stat-box';
      const label = document.createElement('div');
      label.className = 'dash-stat-label';
      label.textContent = stat.label || '';
      const value = document.createElement('div');
      value.className = 'dash-stat-value';
      value.textContent = stat.value != null ? stat.value : '-no_data';
      box.appendChild(label);
      box.appendChild(value);
      grid.appendChild(box);
    }
    card.appendChild(grid);
  }

  if (data.callout) {
    card.appendChild(document.createElement('hr')).className = 'dash-divider';
    const callout = document.createElement('div');
    callout.className = 'dash-callout';
    if (data.callout.label) {
      const lbl = document.createElement('span');
      lbl.className = 'dash-callout-label';
      lbl.textContent = data.callout.label + ': ';
      callout.appendChild(lbl);
    }
    callout.appendChild(document.createTextNode(data.callout.text || ''));
    if (data.callout.delta) {
      const isDown = String(data.callout.delta).trim().startsWith('-');
      const delta = document.createElement('span');
      delta.className = isDown ? 'dash-delta-down' : 'dash-delta-up';
      delta.textContent = ' ' + (isDown ? '▼' : '▲') + String(data.callout.delta).replace('-', '') + (data.callout.delta_label || '');
      callout.appendChild(delta);
    }
    card.appendChild(callout);
  }

  if (data.bar_section && Array.isArray(data.bar_section.rows) && data.bar_section.rows.length) {
    card.appendChild(document.createElement('hr')).className = 'dash-divider';

    const secTitle = document.createElement('div');
    secTitle.className = 'dash-bar-section-title';
    secTitle.textContent = data.bar_section.title || '';
    if (data.bar_section.subtitle) {
      const subEl = document.createElement('span');
      subEl.className = 'dash-subtitle-italic';
      subEl.textContent = ' ' + data.bar_section.subtitle;
      secTitle.appendChild(subEl);
    }
    card.appendChild(secTitle);

    const maxVal = Math.max(...data.bar_section.rows.map(r => Number(r.value) || 0), 1);

    for (const row of data.bar_section.rows) {
      const rowEl = document.createElement('div');
      rowEl.className = 'dash-bar-row';

      const labelEl = document.createElement('div');
      labelEl.className = 'dash-bar-label';
      labelEl.textContent = row.label || '';
      rowEl.appendChild(labelEl);

      const track = document.createElement('div');
      track.className = 'dash-bar-track';
      const fill = document.createElement('div');
      fill.className = 'dash-bar-fill';
      const pct = Math.max(4, Math.round(((Number(row.value) || 0) / maxVal) * 100));
      fill.style.width = pct + '%';
      track.appendChild(fill);
      rowEl.appendChild(track);

      const valuesEl = document.createElement('div');
      valuesEl.className = 'dash-bar-values';
      const valSpan = document.createElement('span');
      valSpan.textContent = row.value != null ? String(row.value) : '';
      valuesEl.appendChild(valSpan);
      if (row.extra) {
        const extraSpan = document.createElement('span');
        extraSpan.textContent = row.extra;
        valuesEl.appendChild(extraSpan);
      }
      rowEl.appendChild(valuesEl);

      card.appendChild(rowEl);
    }
  }

  if (data.footer) {
    const footer = document.createElement('div');
    footer.className = 'dash-footer';
    footer.textContent = (data.footer.label ? data.footer.label + ': ' : '') + (data.footer.value || '');
    card.appendChild(footer);
  }

  const time = document.createElement('span');
  time.className = 'dash-card-time';
  time.textContent = now();
  card.appendChild(time);

  chatEl.appendChild(card);
  chatEl.scrollTop = chatEl.scrollHeight;
}

function extractListCard(text) {
  const match = text.match(/```list-card\s*([\s\S]*?)```/);
  if (!match) return null;
  try {
    const data = JSON.parse(match[1]);
    if (!data || !data.title || !Array.isArray(data.items)) return null;
    return data;
  } catch (e) {
    return null;
  }
}

function renderListCard(data) {
  const card = document.createElement('div');
  card.className = 'message bot dash-card';

  const header = document.createElement('div');
  header.className = 'dash-card-header';
  if (data.icon) {
    const icon = document.createElement('span');
    icon.className = 'dash-card-icon';
    icon.textContent = data.icon;
    header.appendChild(icon);
  }
  const title = document.createElement('span');
  title.className = 'dash-card-title';
  title.textContent = data.title;
  header.appendChild(title);
  card.appendChild(header);

  if (data.intro) {
    const intro = document.createElement('div');
    intro.className = 'dash-list-intro';
    intro.textContent = data.intro;
    card.appendChild(intro);
  }

  data.items.forEach((item, i) => {
    const row = document.createElement('div');
    row.className = 'dash-list-item';

    const badge = document.createElement('div');
    badge.className = 'dash-list-badge';
    badge.textContent = String(i + 1);
    row.appendChild(badge);

    const body = document.createElement('div');
    body.className = 'dash-list-body';

    const primary = document.createElement('div');
    primary.className = 'dash-list-primary';
    primary.textContent = item.primary || '';
    body.appendChild(primary);

    if (Array.isArray(item.fields) && item.fields.length) {
      const fields = document.createElement('div');
      fields.className = 'dash-list-fields';
      for (const f of item.fields) {
        const span = document.createElement('span');
        span.textContent = f;
        fields.appendChild(span);
      }
      body.appendChild(fields);
    }

    row.appendChild(body);
    card.appendChild(row);
  });

  if (data.footer) {
    const footer = document.createElement('div');
    footer.className = 'dash-list-footer';
    footer.textContent = data.footer;
    card.appendChild(footer);
  }

  const time = document.createElement('span');
  time.className = 'dash-card-time';
  time.textContent = now();
  card.appendChild(time);

  chatEl.appendChild(card);
  chatEl.scrollTop = chatEl.scrollHeight;
}
function extractSearchCard(text) {
  const match = text.match(/```search-card\s*([\s\S]*?)```/);
  if (!match) return null;
  try {
    const data = JSON.parse(match[1]);
    if (!data || !data.title || !Array.isArray(data.items)) return null;
    return data;
  } catch (e) {
    return null;
  }
}

function renderSearchCard(data) {
  const card = document.createElement('div');
  card.className = 'message bot search-card';

  const header = document.createElement('div');
  header.className = 'search-card-header';
  header.textContent = (data.icon || '🌐') + ' ' + data.title;
  card.appendChild(header);

  if (data.subtitle) {
    const sub = document.createElement('div');
    sub.className = 'search-card-subtitle';
    sub.textContent = data.subtitle;
    card.appendChild(sub);
  }

  const itemsWrap = document.createElement('div');
  itemsWrap.className = 'search-card-items';
  data.items.forEach(item => {
    const row = document.createElement('div');
    row.className = 'search-card-item';
    const name = document.createElement('strong');
    name.textContent = item.name || '';
    row.appendChild(name);

    if (item.detail) {
      const detail = document.createElement('span');
      detail.textContent = item.detail;
      row.appendChild(detail);
    } else if (Array.isArray(item.stats)) {
      const statsWrap = document.createElement('div');
      statsWrap.className = 'search-card-stats';
      item.stats.forEach(s => {
        const pill = document.createElement('span');
        pill.className = 'search-card-stat-pill';
        pill.textContent = `${s.label}: ${s.value}`;
        statsWrap.appendChild(pill);
      });
      row.appendChild(statsWrap);
    }
    itemsWrap.appendChild(row);
  });
  card.appendChild(itemsWrap);

  if (data.footer) {
    const footer = document.createElement('div');
    footer.className = 'search-card-footer';
    footer.textContent = data.footer;
    card.appendChild(footer);
  }

  chatEl.appendChild(card);
  chatEl.scrollTop = chatEl.scrollHeight;
}

function showSuggestions(list) {
  suggestionsEl.innerHTML = '';
  list.forEach((item, i) => {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.textContent = item.label;
    btn.style.animationDelay = (i * 0.04) + 's';
    btn.onclick = () => {

      suggestionsEl.classList.remove('open');
      suggestionsEl.innerHTML = '';
      if (item.action) {
        item.action();
      } else {
        input.value = item.send;
        handleSend();
      }
    };
    suggestionsEl.appendChild(btn);
  });
  suggestionsEl.classList.add('open');
}

function start() {
  chatEl.innerHTML = '';
  state = { mode: 'normal', activationCode: null, role: null, waitingForCode: false, history: [] };
  statusEl.textContent = 'General Mode';
  modeBadge.textContent = 'Normal';
  modeBadge.classList.remove('premium');

  // ===== DISCLAIMER (put it here) =====

  addMessage(
    `Hello! 👋\n\nI'm **Sahasra AI Assistant**.\n\nYou can ask general questions about hospitals and doctors.\n\nHave an activation code? Enter it to access your hospital data.`,
    'bot'
  );

  showSuggestions([
    { label: 'Doctors at Apollo Kukatpally', send: 'What doctors work at Apollo Kukatpally?' },
    { label: 'Enter Activation Code', send: 'Enter activation code' }
  ]);
}

function handleSend() {
  const text = input.value.trim();
  if (!text) return;
  addMessage(text, 'user');
  input.value = '';
  processMessage(text);
}

async function downloadCollectionExcel(period, reportType, location) {
  addMessage('Generating Excel export...', 'bot');

  const payload = {
    period: period || "today",
    report_type: reportType || "collection",
    activation_code: state.activationCode ? String(state.activationCode) : "",
    location: location ? String(location) : ""
  };
  console.log("EXCEL PAYLOAD", payload);

  try {
    const response = await fetch("http://127.0.0.1:8000/generate-excel", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });

    if (!response.ok) {
      const errText = await response.text();
      console.log("EXCEL ERROR", response.status, errText);
      addMessage("Excel failed (" + response.status + "): " + errText, "bot");
      return;
    }

    const blob = await response.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "collection_" + (period || "today") + ".xlsx";
    document.body.appendChild(a);
    a.click();
    a.remove();
    window.URL.revokeObjectURL(url);

    addMessage("✅ Excel downloaded.", "bot");
  } catch (err) {
    console.error(err);
    addMessage("Could not download Excel. Try again.", "bot");
  }
}

function showExcelMenu() {
  if (state.mode  === 'premium'){
  if (suggestionsEl.classList.contains('open') && suggestionsEl.dataset.menu === 'excel') {
    suggestionsEl.classList.remove('open');
    suggestionsEl.innerHTML = '';
    return;
  }
  showSuggestions([
    { label: 'Collection · Today', action: () => downloadCollectionExcel('today', 'collection') },
    { label: 'Collection · Yesterday', action: () => downloadCollectionExcel('yesterday', 'collection') },
    { label: 'Collection · This month', action: () => promptForLocationThenDownload('this_month', 'collection') },
    { label: 'Top tests · Today', action: () => downloadCollectionExcel('today', 'top_tests') },
    { label: 'Refunds · Today', action: () => downloadCollectionExcel('today', 'refunds') },
    { label: 'Registrations · Today', action: () => downloadCollectionExcel('today', 'registrations') },
  ]);
  suggestionsEl.dataset.menu = 'excel';
}}
async function promptForLocationThenDownload(period, reportType) {
  addMessage('Loading branches...', 'bot');
  try {
    const response = await fetch("http://127.0.0.1:8000/locations", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ activation_code: state.activationCode ? String(state.activationCode) : "" })
    });
    const data = await response.json();
    const locations = data.locations || [];

    if (!locations.length) {
      addMessage('Could not load branch list.', 'bot');
      return;
    }

    showSuggestions(
      locations.map(loc => ({
        label: loc,
        action: () => downloadCollectionExcel(period, reportType, loc)
      }))
    );
  } catch (err) {
    console.error(err);
    addMessage('Could not load branch list.', 'bot');
  }
}
async function processMessage(text) {
  // alert('processMessage called with: ' + text);
  const q = text.toLowerCase();
  // Was 4 rigid exact phrases ("download pdf", "generate pdf", ...) which
  // missed anything phrased naturally, like "download a report pdf about
  // X" — "download" and "pdf" are both there, just not adjacent, so it
  // fell through to the LLM instead of triggering the PDF export. Now
  // matches "pdf" plus any reasonable action word, in any order/spacing.
  const mentionsPdf = q.includes('pdf');
  const hasActionWord = ['download', 'generate', 'export', 'give me', 'create', 'make', 'report'].some(w => q.includes(w));

  if (q === '/limit') {
    try {
      const res = await fetch('http://127.0.0.1:8000/usage-status', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ activation_code: state.activationCode || '' }),
      });
      const data = await res.json();
      if (data.error) {
        addMessage(data.error, 'bot');
      } else {
        addMessage(
          `⏱️ **Token Usage** (${data.institution_code})\n\n` +
          `**${data.used.toLocaleString()}** / **${data.limit.toLocaleString()}** tokens used this ${data.period_type} (**${data.pct}%**)\n\n` +
          `Remaining: **${data.remaining.toLocaleString()}**`,
          'bot'
        );
      }
    } catch (err) {
      addMessage('Could not fetch usage status.', 'bot');
    }
    return;
  }


  if (mentionsPdf && hasActionWord) {
    // If the request names a specific patient (UHID pattern, e.g.
    // KDX26929648), fetch a REAL fresh report for that one patient
    // instead of just re-wrapping whatever the last chat answer said.
    // This is what makes it a "Smart Report" rather than a generic
    // PDF-ification of old text — a targeted database lookup, not a
    // re-hash of a previous unrelated answer (e.g. a 5-patient list).
    const uhidMatch = text.match(/\b([A-Z]{1,6}\d{3,})\b/i);
    if (uhidMatch) {
      await downloadPatientReport(uhidMatch[1]);
      return;
    }

    if (!state.lastAnswer) {
      addMessage('Please ask a data question first, then request the PDF.', 'bot');
      return;
    }
    await downloadPdf(state.lastAnswer);
    return;
}
  // ===== EXCEL =====
  if (
    (q.includes('excel') || q.includes('xlsx')) &&
    (q.includes('export') || q.includes('download') || q.includes('generate') || q.includes('excel'))
  ) {
    let period = 'today';
    if (q.includes('yesterday')) period = 'yesterday';
    else if (q.includes('last month')) period = 'last_month';
    else if (q.includes('this month')) period = 'this_month';
    else if (q.includes('this week')) period = 'this_week';

    let reportType = 'collection';
    if (q.includes('top test')) reportType = 'top_tests';
    else if (q.includes('refund')) reportType = 'refunds';
    else if (q.includes('registration') || q.includes('register')) reportType = 'registrations';

    await downloadExcel(period, reportType);
    return;
  }


  // ===== EXIT PREMIUM =====
  if (q === 'exit' || q.includes('exit premium') || q.includes('logout') || q.includes('switch to normal')) {
    if (state.activationCode) {
      fetch('http://192.168.0.163:8000/release-device', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ activation_code: state.activationCode })
      }).catch(() => {});
    }
    state.mode = 'normal';
    document.getElementById('excelBtn').style.display = 'none';
    state.activationCode = null;
    state.role = null;
    state.hospitalName = null;
    state.history = [];

    statusEl.textContent = 'General Mode';
    modeBadge.textContent = 'Normal';
    modeBadge.classList.remove('premium');

    addMessage(`You have exited Premium mode.\nNow in **Normal Mode**.`, 'bot');

    showSuggestions([
      { label: 'Doctors at Apollo Kukatpally', send: 'What doctors work at Apollo Kukatpally?' },
      { label: 'Enter Activation Code', send: 'Enter activation code' }
    ]);
    return;
  }


  // User wants to enter code
  if (q.includes('enter activation code') || q.includes('activation code')) {
    state.waitingForCode = true;
    addMessage(`Please type your activation code.`, 'bot');
    showSuggestions([]);
    return;
  }

  // Waiting for code
  if (state.waitingForCode) {
        if (q === 'cancel') {
      state.waitingForCode = false;
      addMessage('Cancelled.', 'bot');
      showSuggestions([
        { label: 'Enter Activation Code', send: 'Enter activation code' },
        { label: 'Continue in Normal Mode', send: 'hi' }
      ]);
      return;
    }
    statusEl.textContent = 'Validating code...';

    try {
      const response = await fetch(API_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          question: "validate",
          activation_code: text,
          chat_history: [],
          device_fingerprint: DEVICE_FINGERPRINT
        })
      });

      const data = await response.json();

      if (data.status === 'success' && data.mode === 'otp_required') {
        state.pendingActivationCode = text.toUpperCase();
        state.waitingForCode = false;
        state.waitingForOtp = true;
        addMessage(data.answer, 'bot');
        showSuggestions([]);
        return;
      }

      if (data.status === 'success' && data.mode === 'premium') {
        state.mode = 'premium';
        document.getElementById('excelBtn').style.display = 'inline-block';
        state.activationCode = text.toUpperCase();   // ← MUST save the code
        state.role = data.role;
        state.institutionType = data.institution_type || 'diagnostic';
        // alert('institutionType: ' + state.institutionType);
        state.hospitalName = data.hospital_name || data.hospitalName || null;
        state.waitingForCode = false;        
        statusEl.textContent = `Premium • ${data.role}`;
        modeBadge.textContent = 'Premium';
        modeBadge.classList.add('premium');

        addMessage(
          `✅ **Premium activated**\n\nHospital: **${data.hospital_name || 'Unknown'}**\nRole: **${data.role.toUpperCase()}**\nPlan: **${data.plan || 'Standard'}**\nYou now have access to hospital live data.`,
          'bot'
        );

        if (state.institutionType === 'hospital') {
          const rolesButtons = {
            doctor: [
              { label: 'Bed occupancy', send: 'how many beds are occupied right now' },
              { label: 'Currently admitted', send: 'who is admitted currently' },
            ],
            reception: [
              { label: 'Bed occupancy', send: 'how many beds are occupied right now' },
              { label: 'Currently admitted', send: 'who is admitted currently' },
            ],
            admin: [
              { label: 'Bed occupancy', send: 'how many beds are occupied right now' },
              { label: 'Currently admitted', send: 'who is admitted currently' },
            ],
          };
          const buttons = rolesButtons[state.role] || rolesButtons.admin;
          showSuggestions(buttons);
        } else {
          showSuggestions([
            { label: 'Show all patients', send: 'Show me all patients' },
            { label: "Today's collection", send: "Today's collection data" }
          ]);
        }
      }else {
       // state.waitingForCode = false;
        addMessage(data.answer || `❌ Invalid or expired activation code. Try again, or type "cancel" to stop.`, 'bot');
        showSuggestions([
          { label: 'Enter Activation Code', send: 'Enter activation code' },
          { label: 'Continue in Normal Mode', send: 'hi' }
        ]);
      }
    } catch (err) {
      addMessage('Could not validate the code. Please try again.', 'bot');
    }
    return;
  }

  if (state.waitingForOtp) {
    statusEl.textContent = 'Verifying code...';
    try {
      const response = await fetch('http://192.168.0.163:8000/verify-otp', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          activation_code: state.pendingActivationCode,
          otp: text
        })
      });
      const data = await response.json();

      if (data.status === 'success' && data.mode === 'premium') {
        state.mode = 'premium';
        document.getElementById('excelBtn').style.display = 'inline-block';
        state.activationCode = state.pendingActivationCode;
        state.role = data.role;
        state.institutionType = data.institution_type || 'diagnostic';
        state.hospitalName = data.hospital_name || null;
        state.waitingForOtp = false;
        statusEl.textContent = `Premium • ${data.role}`;
        modeBadge.textContent = 'Premium';
        modeBadge.classList.add('premium');

        addMessage(
          `✅ **Premium activated**\n\nHospital: **${data.hospital_name || 'Unknown'}**\nRole: **${data.role.toUpperCase()}**\nPlan: **${data.plan || 'Standard'}**\nYou now have access to hospital live data.`,
          'bot'
        );

        if (state.institutionType === 'hospital') {
          showSuggestions([
            { label: 'Bed occupancy', send: 'how many beds are occupied right now' },
            { label: 'Currently admitted', send: 'who is admitted currently' },
          ]);
        } else {
          showSuggestions([
            { label: 'Show all patients', send: 'Show me all patients' },
            { label: "Today's collection", send: "Today's collection data" }
          ]);
        }
      } else {
        addMessage(data.answer || 'Incorrect code. Try again.', 'bot');
      }
    } catch (err) {
      addMessage('Could not verify the code. Please try again.', 'bot');
    }
    return;
  }

  // Normal continue
  if (q === 'hi' || q.includes('continue without')) {
    state.waitingForCode = false;
    addMessage(`Continuing in Normal Mode.`, 'bot');
    showSuggestions([
      { label: 'Doctors at Apollo Kukatpally', send: 'What doctors work at Apollo Kukatpally?' },
      { label: 'Enter Activation Code', send: 'Enter activation code' }
    ]);
    return;
  }

  // Call backend
  await callBackend(text);
}

async function callBackend(question) {
  statusEl.textContent = 'Thinking...';
  state.history.push({ role: 'user', content: question });

  const typingEl = document.createElement('div');
  typingEl.className = 'message bot typing-indicator';
  typingEl.innerHTML = '<span class="typing-dots"><span></span><span></span><span></span></span>';
  chatEl.appendChild(typingEl);
  chatEl.scrollTop = chatEl.scrollHeight;

  try {
    const response = await fetch(API_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        question: question,
        activation_code: state.activationCode,
        chat_history: state.history,
        device_fingerprint: DEVICE_FINGERPRINT
      })
    });

    const data = await response.json();
    console.log("Backend response:", data);

    typingEl.remove();
    if (data.usage_warning) {
      document.getElementById('usageBannerText').textContent = data.usage_warning;
      document.getElementById('usageBanner').style.display = 'flex';
    }
    if (data.status === 'success') {
      addMessage(data.answer, 'bot');
      state.history.push({ role: 'assistant', content: data.answer });
      state.lastAnswer = data.answer;   // for PDF later
      saveSession();
    } else {
      addMessage(data.answer || 'Something went wrong.', 'bot');
    }

  } catch (error) {
    typingEl.remove();
    addMessage('Could not connect to the AI server.', 'bot');
    console.error(error);
  }
  // Restore status
  if (state.mode === 'premium') {
    statusEl.textContent = `Premium • ${state.role}`;
  } else {
    statusEl.textContent = 'General Mode';
  }

  // Suggestions
if (state.mode === 'premium' && state.institutionType === 'hospital') {
    const rolesButtons = {
      doctor: [
        { label: 'Bed occupancy', send: 'how many beds are occupied right now' },
        { label: 'Currently admitted', send: 'who is admitted currently' },
        { label: "Today's OPD list (soon)", send: null },
        { label: 'Pending lab reports (soon)', send: null },
      ],
      reception: [
        { label: 'Bed occupancy', send: 'how many beds are occupied right now' },
        { label: 'Currently admitted', send: 'who is admitted currently' },
        { label: 'Book appointment (soon)', send: null },
        { label: 'Patient registration (soon)', send: null },
      ],
      admin: [
        { label: 'Bed occupancy', send: 'how many beds are occupied right now' },
        { label: 'Currently admitted', send: 'who is admitted currently' },
        { label: 'Revenue dashboard (soon)', send: null },
        { label: 'Outstanding bills (soon)', send: null },
      ],
    };
    const buttons = rolesButtons[state.role] || rolesButtons.admin;
    showSuggestions(buttons.map(b => ({
      label: b.label,
      action: b.send ? null : () => addMessage("This feature isn't built yet — coming soon.", 'bot'),
      send: b.send,
    })));
} else if (state.mode === 'premium') {
    showSuggestions([
      { label: 'Show all patients', send: 'Show me all patients' },
      { label: "Today's collection", send: "Today's collection data" },
      { label: 'TAT dashboard', send: 'TAT dashboard today' }
    ]);
} else {
    showSuggestions([
      { label: 'Doctors at Apollo Kukatpally', send: 'What doctors work at Apollo Kukatpally?' },
      { label: 'Enter Activation Code', send: 'Enter activation code' }
    ]);
  }
}
// ===== SESSION PERSISTENCE =====
function saveSession() {
  localStorage.setItem('sahasra_session', JSON.stringify({
    mode: state.mode,
    activationCode: state.activationCode,
    role: state.role,
    hospitalName: state.hospitalName || null,
    history: state.history
  }));
}
async function downloadPdf(answerText) {
  addMessage('Generating PDF report...', 'bot');

  const lines = answerText
    .split('\n')
    .map(l => l.replace(/<[^>]*>/g, '').trim())
    .filter(l => l.length > 0);

  try {
    const response = await fetch('http://127.0.0.1:8000/generate-pdf', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        title: 'Sahasra AI Report',
        hospital_name: state.hospitalName || 'Hospital',
        role: state.role || 'Staff',
        activation_code: state.activationCode || '',
        content_lines: lines
      })
    });

    if (!response.ok) {
      addMessage('Failed to generate PDF.', 'bot');
      return;
    }

    const blob = await response.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'sahasra_report.pdf';
    document.body.appendChild(a);
    a.click();
    a.remove();
    window.URL.revokeObjectURL(url);

    addMessage('✅ PDF downloaded successfully.', 'bot');
  } catch (err) {
    addMessage('Could not download PDF. Please try again.', 'bot');
    console.error(err);
  }
}

async function downloadPatientReport(patientIdentifier) {
  addMessage(`Generating Smart Report for ${patientIdentifier}...`, 'bot');

  try {
    const response = await fetch('http://127.0.0.1:8000/generate-patient-report', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        patient_identifier: patientIdentifier,
        activation_code: state.activationCode || ''
      })
    });

    if (!response.ok) {
      const err = await response.json().catch(() => ({}));
      addMessage(err.detail || 'Failed to generate the patient report.', 'bot');
      return;
    }

    const blob = await response.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `patient_report_${patientIdentifier}.pdf`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    window.URL.revokeObjectURL(url);

    addMessage('✅ Patient report downloaded successfully.', 'bot');
  } catch (err) {
    addMessage('Could not download the patient report. Please try again.', 'bot');
    console.error(err);
  }
}

function loadSession() {
  const raw = localStorage.getItem('sahasra_session');
  if (!raw) return false;

  try {
    const saved = JSON.parse(raw);
    state.mode = saved.mode || 'normal';
    state.activationCode = saved.activationCode || null;
    state.role = saved.role || null;
    state.hospitalName = saved.hospitalName || null;
    state.history = saved.history || [];

    if (state.mode === 'premium') {
      statusEl.textContent = `Premium • ${state.role}${state.hospitalName ? ' • ' + state.hospitalName : ''}`;
      modeBadge.textContent = 'Premium';
      modeBadge.classList.add('premium');
    }
    return true;
  } catch (e) {
    return false;
  }
}

function clearSession() {
  localStorage.removeItem('sahasra_session');
}

start();
</script>
</body>
</html>