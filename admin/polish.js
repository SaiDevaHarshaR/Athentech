/*
 * Sahasra Admin — behaviour layer. Load AFTER app.js, whitelabel.js and row-actions.js:
 *     <script src="polish.js"></script>
 * Everything here is additive and defensive: if an element is missing it is skipped.
 */
(function () {
  'use strict';

  var PATHS = {
    dashboard: '<rect width="7" height="9" x="3" y="3" rx="1"/><rect width="7" height="5" x="14" y="3" rx="1"/><rect width="7" height="9" x="14" y="12" rx="1"/><rect width="7" height="5" x="3" y="16" rx="1"/>',
    licenses: '<circle cx="7.5" cy="15.5" r="5.5"/><path d="m21 2-9.6 9.6"/><path d="m15.5 7.5 3 3L22 7l-3-3"/>',
    institutions: '<path d="M6 22V4a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v18Z"/><path d="M6 12H4a2 2 0 0 0-2 2v6a2 2 0 0 0 2 2h2"/><path d="M18 9h2a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2h-2"/><path d="M10 6h4"/><path d="M10 10h4"/><path d="M10 14h4"/><path d="M10 18h4"/>',
    audit: '<circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>',
    analytics: '<path d="M3 3v18h18"/><path d="M18 17V9"/><path d="M13 17V5"/><path d="M8 17v-3"/>',
    roles: '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>',
    settings: '<line x1="21" x2="14" y1="4" y2="4"/><line x1="10" x2="3" y1="4" y2="4"/><line x1="21" x2="12" y1="12" y2="12"/><line x1="8" x2="3" y1="12" y2="12"/><line x1="21" x2="16" y1="20" y2="20"/><line x1="12" x2="3" y1="20" y2="20"/><line x1="14" x2="14" y1="2" y2="6"/><line x1="8" x2="8" y1="10" y2="14"/><line x1="16" x2="16" y1="18" y2="22"/>',
    chatbotSettings: '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>',
    search: '<circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>',
    bell: '<path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9"/><path d="M10.3 21a1.94 1.94 0 0 0 3.4 0"/>',
    chevron: '<path d="m6 9 6 6 6-6"/>',
    sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2"/><path d="M12 20v2"/><path d="m4.93 4.93 1.41 1.41"/><path d="m17.66 17.66 1.41 1.41"/><path d="M2 12h2"/><path d="M20 12h2"/><path d="m6.34 17.66-1.41 1.41"/><path d="m19.07 4.93-1.41 1.41"/>',
    moon: '<path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"/>',
    plus: '<path d="M5 12h14"/><path d="M12 5v14"/>',
    refresh: '<path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/><path d="M8 16H3v5"/>',
    zap: '<path d="M13 2 3 14h9l-1 8 10-12h-9l1-8z"/>',
    alert: '<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/><path d="M12 9v4"/><path d="M12 17h.01"/>',
    logout: '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" x2="9" y1="12" y2="12"/>',
    up: '<path d="m5 12 7-7 7 7"/><path d="M12 19V5"/>',
    down: '<path d="M12 5v14"/><path d="m19 12-7 7-7-7"/>',
    flat: '<path d="M5 12h14"/>',
    download: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" x2="12" y1="15" y2="3"/>',
    check: '<path d="M20 6 9 17l-5-5"/>',
    spark: '<path d="M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9z"/><path d="M19 15l.7 1.8L21.5 17.5l-1.8.7L19 20l-.7-1.8-1.8-.7 1.8-.7z"/>',
    card: '<rect width="20" height="14" x="2" y="5" rx="2"/><line x1="2" x2="22" y1="10" y2="10"/>'
  };
  function icon(name, size) {
    return '<svg class="ic" viewBox="0 0 24 24" aria-hidden="true"' + (size ? ' style="width:' + size + 'px;height:' + size + 'px"' : '') + '>' + (PATHS[name] || '') + '</svg>';
  }
  function $(sel, root) { return (root || document).querySelector(sel); }
  function $$(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }
  function reduced() { return window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches; }
  function getState() { try { return typeof state !== 'undefined' ? state : null; } catch (e) { return null; } }

  /* ------------------------------------------------------------------ theme */
  function currentTheme() { return document.documentElement.getAttribute('data-theme') || 'light'; }
  function setTheme(t) {
    document.documentElement.setAttribute('data-theme', t);
    try { localStorage.setItem('adminTheme', t); } catch (e) {}
    var b = $('#themeToggle'); if (b) { b.innerHTML = icon(t === 'dark' ? 'sun' : 'moon'); b.setAttribute('aria-label', t === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'); b.title = b.getAttribute('aria-label'); }
  }
  function initTheme() {
    var saved = null; try { saved = localStorage.getItem('adminTheme'); } catch (e) {}
    var t = saved || (window.matchMedia && matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
    var profile = $('.admin-profile');
    if (profile && !$('#themeToggle')) {
      var b = document.createElement('button'); b.id = 'themeToggle'; b.type = 'button'; b.className = 'icon-btn';
      b.addEventListener('click', function () { setTheme(currentTheme() === 'dark' ? 'light' : 'dark'); });
      profile.insertBefore(b, profile.firstChild);
    }
    setTheme(t);
  }

  /* ------------------------------------------------------------------ icons */
  function decorateIcons() {
    $$('.nav-item[data-page]').forEach(function (b) { var s = $('span', b); if (s && !s.dataset.ic) { s.innerHTML = icon(b.dataset.page); s.dataset.ic = '1'; } });
    $$('.brand-mark').forEach(function (m) { if (!m.dataset.ic) { m.innerHTML = icon('spark'); m.dataset.ic = '1'; } });
    var gs = $('.global-search > span'); if (gs && !gs.dataset.ic) { gs.innerHTML = icon('search'); gs.dataset.ic = '1'; }
    var gi = $('#globalSearch'); if (gi) { gi.setAttribute('readonly', ''); gi.setAttribute('aria-label', 'Open command menu'); gi.placeholder = 'Search or jump to…'; }
    var kb = $('.global-search kbd'); if (kb) kb.textContent = /Mac|iPhone|iPad/.test(navigator.platform) ? '⌘ K' : 'Ctrl K';
    var bell = $('#notificationBell'); if (bell && !bell.dataset.ic) { var dot = $('#notificationDot', bell); bell.innerHTML = icon('bell'); if (dot) bell.appendChild(dot); bell.dataset.ic = '1'; }
    var chev = $('#adminProfileBtn > span'); if (chev && !chev.dataset.ic) { chev.innerHTML = icon('chevron', 14); chev.dataset.ic = '1'; chev.style.cssText = 'display:grid;place-items:center;color:var(--muted)'; }
    var lo = $('#adminLogoutBtn'); if (lo && !lo.dataset.ic) { lo.innerHTML = '<span style="display:inline-flex;align-items:center;gap:8px">' + icon('logout', 15) + 'Log out</span>'; lo.dataset.ic = '1'; }
    var metricIcons = { 'Active Licenses': 'licenses', 'Active Hospitals': 'institutions', 'Queries Today': 'zap', 'Failed Validations': 'alert', 'OpenAI Tokens (30d)': 'zap' };
    $$('.metric-card').forEach(function (c) { var label = ($('.metric-top span', c) || {}).textContent, mi = $('.metric-icon', c); if (mi && !mi.dataset.ic && metricIcons[label && label.trim()]) { mi.innerHTML = icon(metricIcons[label.trim()]); mi.dataset.ic = '1'; } });
    function decorate(btn, name, label) { if (btn && !btn.dataset.ic) { btn.innerHTML = icon(name) + '<span>' + label + '</span>'; btn.dataset.ic = '1'; } }
    decorate($('#refreshDashboard'), 'refresh', 'Refresh'); decorate($('#dashboardAdd'), 'plus', 'Add institution'); decorate($('#generateLicense'), 'plus', 'Generate license'); decorate($('#tokensBtn'), 'zap', 'Tokens');
    $$('.registry-search > span').forEach(function (s) { if (!s.dataset.ic) { s.innerHTML = icon('search', 15); s.dataset.ic = '1'; s.style.cssText = 'display:grid;place-items:center'; } });
    var actIcons = { '◇': 'chatbotSettings', '!': 'alert', '•': 'check' };
    $$('.activity-icon').forEach(function (a) { var g = a.textContent.trim(); if (!a.dataset.ic && actIcons[g]) { a.innerHTML = icon(actIcons[g], 16); a.dataset.ic = '1'; a.style.display = 'grid'; a.style.placeItems = 'center'; if (g === '!') { a.style.background = 'var(--red-soft)'; a.style.color = 'var(--red)'; } } });
    $$('.empty').forEach(function (e) { if (!e.dataset.ic && !e.children.length) { e.dataset.ic = '1'; e.innerHTML = '<div style="display:grid;place-items:center;gap:10px"><span style="width:40px;height:40px;border-radius:12px;background:var(--surface-2);display:grid;place-items:center;color:var(--faint)">' + icon('search', 20) + '</span><span>' + e.textContent + '</span></div>'; } });
  }

  /* ------------------------------------------------------------- KPI deltas */
  function dayKey(d) { return new Date(d).toDateString(); }
  function chip(kind, text, arrow) { return '<span class="delta ' + kind + '">' + (arrow ? icon(arrow) : '') + text + '</span>'; }
  function pctDelta(cur, prev) { if (!prev) return cur ? { kind: 'up', text: 'New', arrow: 'up' } : { kind: 'flat', text: '—', arrow: null }; var p = Math.round((cur - prev) / prev * 100); return { kind: p > 0 ? 'up' : p < 0 ? 'down' : 'flat', text: (p > 0 ? '+' : '') + p + '%', arrow: p > 0 ? 'up' : p < 0 ? 'down' : 'flat' }; }
  function setBottom(id, html) { var v = document.getElementById(id); if (!v) return; var card = v.closest('.metric-card'); var b = card && $('.metric-bottom', card); if (b && b.dataset.k !== html) { b.className = 'metric-bottom'; b.innerHTML = html; b.dataset.k = html; } }
  function refreshKpis() {
    var s = getState(); if (!s) return;
    var events = s.auditEvents || [], lic = s.licenses || [], inst = s.institutions || [];
    var today = dayKey(Date.now()), yest = dayKey(Date.now() - 864e5);
    var q = events.filter(function (e) { return e.event === 'premium_query'; });
    var qt = q.filter(function (e) { return dayKey(e.ts) === today; }).length, qy = q.filter(function (e) { return dayKey(e.ts) === yest; }).length;
    var d = pctDelta(qt, qy); setBottom('queriesToday', chip(d.kind, d.text, d.arrow) + '<small>vs yesterday (' + qy.toLocaleString() + ')</small>');
    var now = Date.now(), f7 = 0, fp = 0;
    events.filter(function (e) { return e.event === 'invalid_code_attempt'; }).forEach(function (e) { var age = now - new Date(e.ts).getTime(); if (age <= 7 * 864e5) f7++; else if (age <= 14 * 864e5) fp++; });
    var fd = pctDelta(f7, fp); setBottom('failedValidations', chip(fd.kind === 'up' ? 'down' : fd.kind === 'down' ? 'up' : 'flat', fd.text, fd.arrow) + '<small>' + f7 + ' in last 7 days</small>');
    var active = lic.filter(function (l) { return l.status === 'Active' || l.status === 'Trial'; }).length;
    var soon = lic.filter(function (l) { var t = new Date(l.expiry).getTime() - now; return (l.status === 'Active') && t > 0 && t < 30 * 864e5; }).length;
    setBottom('activeLicenses', '<small>of ' + lic.length + ' total</small>' + (soon ? '<span class="delta down" style="background:var(--orange-soft);color:var(--orange)">' + soon + ' expiring ≤30d</span>' : ''));
    setBottom('activeHospitals', '<small>of ' + inst.length + ' registered</small>');
  }

  /* ------------------------------------------------------ count-up numbers */
  var animating = false;
  function countUp(el) {
    if (reduced() || el.dataset.cu === el.textContent) return;
    var txt = el.textContent, n = parseFloat(txt.replace(/[^0-9.-]/g, ''));
    if (!isFinite(n) || n === 0 || /[A-Za-z]/.test(txt.replace(/[kKmM]$/, ''))) { el.dataset.cu = txt; return; }
    var from = el.dataset.cu ? parseFloat(el.dataset.cu.replace(/[^0-9.-]/g, '')) || 0 : 0, t0 = performance.now(), dur = 650;
    var withCommas = /,/.test(txt);
    animating = true; el.dataset.cu = txt;
    (function step(t) {
      var p = Math.min(1, (t - t0) / dur), e = 1 - Math.pow(1 - p, 3), v = Math.round(from + (n - from) * e);
      el.textContent = withCommas ? v.toLocaleString() : String(v);
      if (p < 1) requestAnimationFrame(step); else { el.textContent = txt; animating = false; }
    })(t0);
  }

  /* ----------------------------------------------------- sortable tables + CSV */
  var sorting = false;
  function cellVal(td) { var t = (td ? td.textContent : '').trim(); var n = parseFloat(t.replace(/[,₹%\s]/g, '')); var d = Date.parse(t); return (!isNaN(n) && /^[#₹\d.,%\s-]+$/.test(t)) ? n : (!isNaN(d) && /\d{4}/.test(t) ? d : t.toLowerCase()); }
  function applySort(table) {
    var tb = $('tbody', table), col = table.dataset.sortCol; if (!tb || col === undefined) return;
    var dir = table.dataset.sortDir === 'desc' ? -1 : 1, rows = $$('tr', tb); if (rows.length < 2 || $('.empty', tb)) return;
    sorting = true;
    rows.sort(function (a, b) { var x = cellVal(a.children[col]), y = cellVal(b.children[col]); return (x > y ? 1 : x < y ? -1 : 0) * dir; }).forEach(function (r) { tb.appendChild(r); });
    sorting = false;
  }
  function decorateTables() {
    $$('.table-panel table').forEach(function (table) {
      var ths = $$('thead th', table);
      ths.forEach(function (th, i) {
        var label = th.textContent.trim().toLowerCase();
        if (!label || label === 'actions' || th.dataset.sortable) return;
        th.dataset.sortable = '1'; th.classList.add('sortable'); th.title = 'Sort by ' + th.textContent.trim();
        th.addEventListener('click', function () {
          var same = table.dataset.sortCol === String(i);
          table.dataset.sortDir = same && table.dataset.sortDir === 'asc' ? 'desc' : 'asc'; table.dataset.sortCol = String(i);
          ths.forEach(function (x) { x.classList.remove('sorted-asc', 'sorted-desc'); }); th.classList.add('sorted-' + table.dataset.sortDir); applySort(table);
        });
      });
      var tb = $('tbody', table);
      if (tb && !tb.dataset.obs) { tb.dataset.obs = '1'; new MutationObserver(function () { if (!sorting) applySort(table); }).observe(tb, { childList: true }); }
    });
    $$('.table-panel .table-header').forEach(function (h) {
      if (h.dataset.export || h.closest('#institutionsPage')) return;
      h.dataset.export = '1'; h.style.alignItems = 'center';
      var b = document.createElement('button'); b.type = 'button'; b.className = 'secondary-btn'; b.style.height = '30px'; b.innerHTML = icon('download') + '<span>Export CSV</span>';
      b.addEventListener('click', function () { exportCsv(h.closest('.table-panel')); }); h.appendChild(b);
    });
  }
  function exportCsv(panel) {
    var table = $('table', panel); if (!table) return;
    var heads = $$('thead th', table), keep = heads.map(function (th) { return th.textContent.trim() && th.textContent.trim().toLowerCase() !== 'actions'; });
    var esc = function (v) { v = String(v == null ? '' : v).replace(/\s+/g, ' ').trim(); return /[",\n]/.test(v) ? '"' + v.replace(/"/g, '""') + '"' : v; };
    var lines = [heads.filter(function (_, i) { return keep[i]; }).map(function (h) { return esc(h.textContent); }).join(',')];
    $$('tbody tr', table).forEach(function (tr) { if ($('.empty', tr)) return; lines.push($$('td', tr).filter(function (_, i) { return keep[i]; }).map(function (td) { return esc(td.textContent); }).join(',')); });
    var name = ((($('.table-header strong', panel) || {}).textContent) || 'export').trim().toLowerCase().replace(/\s+/g, '-');
    var a = document.createElement('a'); a.href = URL.createObjectURL(new Blob(['\ufeff' + lines.join('\n')], { type: 'text/csv;charset=utf-8' })); a.download = name + '-' + new Date().toISOString().slice(0, 10) + '.csv';
    document.body.appendChild(a); a.click(); setTimeout(function () { URL.revokeObjectURL(a.href); a.remove(); }, 500);
    if (typeof toast === 'function') toast('Exported ' + (lines.length - 1) + ' rows');
  }

  /* -------------------------------------------------------- command palette */
  var cmdk, cmdkSel = 0, cmdkItems = [], openedAt = 0;
  function score(q, text) {
    q = q.toLowerCase().trim(); text = String(text || '').toLowerCase(); if (!q) return 1;
    var i = text.indexOf(q); if (i >= 0) return 100 - Math.min(i, 60) + (i === 0 ? 20 : 0);
    var parts = q.split(/\s+/).filter(Boolean);                       // every word must appear somewhere
    return parts.length > 1 && parts.every(function (p) { return text.indexOf(p) >= 0; }) ? 40 : 0;
  }
  function go(page, search) {
    if (typeof navigate === 'function') navigate(page);
    if (search) setTimeout(function () { var inp = $('#' + page + 'Page .registry-search input'); if (inp) { inp.value = search; inp.dispatchEvent(new Event('input', { bubbles: true })); } }, 60);
  }
  function buildItems(q) {
    var out = [], s = getState();
    var nav = $$('.nav-item[data-page]').map(function (b) { return { g: 'Go to', ic: b.dataset.page, t: b.textContent.trim(), run: function () { go(b.dataset.page); } }; });
    var acts = [
      { g: 'Actions', ic: 'plus', t: 'Generate license', run: function () { go('licenses'); setTimeout(function () { if (typeof openLicense === 'function') openLicense(); }, 80); } },
      { g: 'Actions', ic: 'plus', t: 'Add institution', run: function () { go('institutions'); setTimeout(function () { if (typeof openInstitution === 'function') openInstitution(); }, 80); } },
      { g: 'Actions', ic: 'zap', t: 'Manage token limits', run: function () { if (typeof openTokensModal === 'function') openTokensModal(); } },
      { g: 'Actions', ic: 'refresh', t: 'Refresh dashboard', run: function () { go('dashboard'); setTimeout(function () { var b = $('#refreshDashboard'); if (b) b.click(); }, 80); } },
      { g: 'Actions', ic: 'download', t: 'Export current table CSV', run: function () { var p = $('.table-panel:not([hidden])') || $('.table-panel'); if (p) exportCsv(p); } },
      { g: 'Actions', ic: 'audit', t: 'Open audit log', run: function () { go('audit'); } },
      { g: 'Actions', ic: 'roles', t: 'Open roles & permissions', run: function () { go('roles'); } },
      { g: 'Actions', ic: 'settings', t: 'Open settings', run: function () { go('settings'); } },
      { g: 'Actions', ic: 'chatbotSettings', t: 'Open chatbot / white-label', run: function () { go('chatbotSettings'); } },
      { g: 'Actions', ic: 'analytics', t: 'Open analytics', run: function () { go('analytics'); } },
      { g: 'Actions', ic: 'licenses', t: 'Filter active licenses', run: function () { go('licenses'); setTimeout(function () { var inp = $('#licensesPage .registry-search input'); if (inp) { inp.value = 'Active'; inp.dispatchEvent(new Event('input', { bubbles: true })); } }, 80); } },
      { g: 'Actions', ic: 'card', t: 'Copy API base URL', run: function () { var u = (window.API_BASE || location.origin); if (navigator.clipboard) navigator.clipboard.writeText(u); if (typeof toast === 'function') toast('Copied: ' + u); } },
      { g: 'Actions', ic: currentTheme() === 'dark' ? 'sun' : 'moon', t: 'Switch to ' + (currentTheme() === 'dark' ? 'light' : 'dark') + ' theme', run: function () { setTheme(currentTheme() === 'dark' ? 'light' : 'dark'); } },
      { g: 'Actions', ic: 'logout', t: 'Log out', run: function () { var b = $('#adminLogoutBtn'); if (b) b.click(); } }
    ];
    nav.concat(acts).forEach(function (it) { var sc = score(q, it.t); if (sc) { it.sc = sc + (it.g === 'Go to' ? 1 : 0); out.push(it); } });
    if (s && q) {
      (s.institutions || []).forEach(function (i) { var sc = Math.max(score(q, i.name), score(q, i.code), score(q, i.city)); if (sc) out.push({ g: 'Institutions', ic: 'institutions', t: i.name, sub: [i.code, i.city].filter(Boolean).join(' · '), sc: sc, run: function () { go('institutions', i.name); } }); });
      (s.licenses || []).forEach(function (l) { var inst = (s.institutions || []).filter(function (x) { return x.id === l.institutionId; })[0]; var sc = Math.max(score(q, l.code), score(q, l.email), score(q, l.role)); if (sc) out.push({ g: 'Licenses', ic: 'licenses', t: l.code, sub: [inst && inst.name, l.role, l.status].filter(Boolean).join(' · '), sc: sc, run: function () { go('licenses', l.code); } }); });
    }
    var order = { 'Go to': 1, 'Actions': 2, 'Institutions': 3, 'Licenses': 4 };
    return out.sort(function (a, b) { return (order[a.g] - order[b.g]) || (b.sc - a.sc); }).slice(0, 40);
  }
  function renderCmdk() {
    var q = $('input', cmdk).value.trim(), list = $('.cmdk-list', cmdk); cmdkItems = buildItems(q); cmdkSel = Math.min(cmdkSel, Math.max(0, cmdkItems.length - 1));
    if (!cmdkItems.length) { list.innerHTML = '<div class="cmdk-empty">No results for “' + q.replace(/[<>&]/g, '') + '”</div>'; return; }
    var html = '', last = '';
    cmdkItems.forEach(function (it, i) {
      if (it.g !== last) { html += '<div class="cmdk-group">' + it.g + '</div>'; last = it.g; }
      html += '<div class="cmdk-item' + (i === cmdkSel ? ' sel' : '') + '" data-i="' + i + '">' + icon(it.ic) + '<span>' + it.t.replace(/[<>&]/g, '') + '</span>' + (it.sub ? '<small>' + it.sub.replace(/[<>&]/g, '') + '</small>' : '') + '</div>';
    });
    list.innerHTML = html; var sel = $('.cmdk-item.sel', list); if (sel && sel.scrollIntoView) sel.scrollIntoView({ block: 'nearest' });
  }
  function openCmdk() { if (!cmdk) return; openedAt = Date.now(); cmdk.classList.add('open'); var i = $('input', cmdk); i.value = ''; cmdkSel = 0; renderCmdk(); setTimeout(function () { i.focus(); }, 0); }
  function closeCmdk() { if (cmdk) cmdk.classList.remove('open'); }
  function runSel() { var it = cmdkItems[cmdkSel]; if (it) { closeCmdk(); it.run(); } }
  function initCmdk() {
    cmdk = document.createElement('div'); cmdk.id = 'cmdk'; cmdk.setAttribute('role', 'dialog'); cmdk.setAttribute('aria-label', 'Command menu');
    cmdk.innerHTML = '<div class="cmdk-box"><div class="cmdk-input">' + icon('search') + '<input type="text" placeholder="Search pages, institutions, licenses, actions…" autocomplete="off" spellcheck="false"></div><div class="cmdk-list"></div>' +
      '<div class="cmdk-foot"><span><kbd>↑</kbd> <kbd>↓</kbd> navigate</span><span><kbd>↵</kbd> select</span><span><kbd>esc</kbd> close</span></div></div>';
    document.body.appendChild(cmdk);
    cmdk.addEventListener('mousedown', function (e) { if (e.target === cmdk) closeCmdk(); });
    $('input', cmdk).addEventListener('input', function () { cmdkSel = 0; renderCmdk(); });
    $('.cmdk-list', cmdk).addEventListener('mousemove', function (e) { var it = e.target.closest('.cmdk-item'); if (it && +it.dataset.i !== cmdkSel) { cmdkSel = +it.dataset.i; $$('.cmdk-item', cmdk).forEach(function (n) { n.classList.toggle('sel', +n.dataset.i === cmdkSel); }); } });
    $('.cmdk-list', cmdk).addEventListener('click', function (e) { var it = e.target.closest('.cmdk-item'); if (it) { cmdkSel = +it.dataset.i; runSel(); } });
    document.addEventListener('keydown', function (e) {
      var typing = /INPUT|TEXTAREA|SELECT/.test((document.activeElement || {}).tagName || '') && document.activeElement.id !== 'globalSearch' && !cmdk.contains(document.activeElement);
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); if (cmdk.classList.contains('open')) { if (Date.now() - openedAt > 200) closeCmdk(); } else openCmdk(); return; }
      if (e.key === '/' && !typing && !cmdk.classList.contains('open') && !$('.modal-overlay.show')) { e.preventDefault(); openCmdk(); return; }
      if (!cmdk.classList.contains('open')) return;
      if (e.key === 'Escape') { e.preventDefault(); closeCmdk(); }
      else if (e.key === 'ArrowDown') { e.preventDefault(); cmdkSel = Math.min(cmdkItems.length - 1, cmdkSel + 1); renderCmdk(); }
      else if (e.key === 'ArrowUp') { e.preventDefault(); cmdkSel = Math.max(0, cmdkSel - 1); renderCmdk(); }
      else if (e.key === 'Enter') { e.preventDefault(); runSel(); }
    });
    var gs = $('.global-search'); if (gs) gs.addEventListener('click', function (e) { e.preventDefault(); openCmdk(); });
    var gi = $('#globalSearch'); if (gi) gi.addEventListener('focus', function () { gi.blur(); openCmdk(); });
  }

  /* ----------------------------------------------------------------- login */
  function initLogin() {
    var ov = $('#adminLoginOverlay'), card = $('#adminLoginForm'); if (!ov || !card || $('.login-hero', ov)) return;
    var side = document.createElement('div'); side.className = 'login-side'; ov.appendChild(side); side.appendChild(card);
    var hero = document.createElement('div'); hero.className = 'login-hero';
    hero.innerHTML = '<div class="lh-brand"><i>' + icon('spark', 18) + '</i>Sahasra AI</div>' +
      '<div><h2>One console for every hospital’s AI assistant.</h2><p>Issue activation codes, set usage limits, control who sees which data, and audit every question — across all your institutions.</p>' +
      '<ul><li>' + icon('check') + 'Per-institution licenses, limits and audit trail</li><li>' + icon('check') + 'Role-based access to live hospital data</li><li>' + icon('check') + 'White-label chatbots for your clients</li></ul></div>' +
      '<div class="lh-foot">© ' + new Date().getFullYear() + ' AthenTech · Secured admin access</div>';
    ov.insertBefore(hero, side);
    var h1 = $('h1', card), p = $('p', card); if (h1) h1.textContent = 'Welcome back'; if (p) p.textContent = 'Sign in to manage institutions, licenses and roles.';
  }

  /* ------------------------------------------------------------------ boot */
  function run() { decorateIcons(); decorateTables(); refreshKpis(); $$('.metric-card > strong').forEach(function (el) { if (!animating) countUp(el); }); }
  var queued = false;
  function schedule() { if (queued) return; queued = true; requestAnimationFrame(function () { queued = false; try { run(); } catch (e) { console.warn('[polish]', e); } }); }
  function init() {
    initTheme(); 
      // accent hairline on main on route change
  try {
    var main = document.querySelector('main') || document.querySelector('.shell main');
    if (main && !main.dataset.t1) {
      main.dataset.t1 = '1';
      new MutationObserver(function () {
        main.classList.remove('page-enter');
        void main.offsetWidth;
        main.classList.add('page-enter');
      }).observe(main, { childList: true });
    }
  } catch (e) {}
  initLogin(); initCmdk(); run();
    new MutationObserver(function (m) { if (!animating) schedule(); }).observe(document.body, { childList: true, subtree: true, characterData: true });
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
  window.__polish = { setTheme: setTheme, openCmdk: openCmdk, refreshKpis: refreshKpis };
})();
