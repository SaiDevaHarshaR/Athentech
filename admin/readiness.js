/* Admin > Settings > "Client Readiness" card (additive). One click checks every client: database reachable, tables/columns present,
   data fresh, white-label + B2B settings complete. Plain-language results, worst clients first. Text inserted with textContent only. */
(function () {
  'use strict';
  var S = { open: false, data: null, err: '', timer: null, busy: false };
  var root, bodyEl, badge, subEl;
  function api(path, opt) {
    var base = (typeof API_BASE !== 'undefined' && API_BASE) ? API_BASE : '';
    var tok = (typeof getAdminToken === 'function') ? getAdminToken() : '';
    opt = opt || {};
    opt.headers = Object.assign({ 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + tok }, opt.headers || {});
    return fetch(base + path, opt).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (j) {
        if (r.status === 401) throw new Error('Your session has ended - please sign in again.');
        if (!r.ok) throw new Error(j.detail || j.message || ('Request failed (' + r.status + ')'));
        return j;
      });
    });
  }
  function h(tag, attrs) {
    var e = document.createElement(tag), i = 2; attrs = attrs || {};
    Object.keys(attrs).forEach(function (k) {
      if (k === 'class') e.className = attrs[k]; else if (k === 'text') e.textContent = attrs[k];
      else if (k.slice(0, 2) === 'on') e.addEventListener(k.slice(2), attrs[k]);
      else if (attrs[k] !== false && attrs[k] != null) e.setAttribute(k, attrs[k] === true ? '' : attrs[k]);
    });
    for (; i < arguments.length; i++) { var c = arguments[i]; if (c == null || c === false) continue; e.appendChild(typeof c === 'string' ? document.createTextNode(c) : c); }
    return e;
  }
  var COL = { ok: '#16a34a', warn: '#d97706', fail: '#dc2626' }, ICO = { ok: '✔', warn: '⚠', fail: '✖' };
  var CSS = '.rd-card{grid-column:1/-1;padding:0!important;overflow:hidden;min-width:0;max-width:100%}.rd-card *{min-width:0}\
.rd-head{all:unset;box-sizing:border-box;display:flex;align-items:center;gap:14px;width:100%;padding:20px 22px;cursor:pointer}\
.rd-head:focus-visible{outline:2px solid var(--primary,#6a5cf6);outline-offset:-2px;border-radius:12px}\
.rd-ico{flex:none;width:42px;height:42px;border-radius:12px;display:grid;place-items:center;font-size:20px;background:linear-gradient(135deg,rgba(34,197,94,.22),rgba(34,211,238,.18))}\
.rd-title{flex:1}.rd-title b{display:block;font:650 15px var(--font,system-ui);color:var(--ink,#111)}.rd-title small{display:block;margin-top:2px;font-size:12.5px;color:var(--muted,#667);overflow-wrap:anywhere}\
.rd-badge{flex:none;font-size:12px;font-weight:700;padding:4px 10px;border-radius:99px;background:var(--accent-soft,#eeeaff);color:var(--accent-ink,#4a3dd1)}\
.rd-body{display:none;padding:4px 22px 22px;border-top:1px solid var(--border,#e6e6ec)}.rd-card.open .rd-body{display:block}\
.rd-bar{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin:16px 0}\
.rd-btn{border:0;border-radius:10px;padding:10px 16px;font:650 13px var(--font,system-ui);cursor:pointer;background:var(--primary,#6a5cf6);color:#fff}.rd-btn[disabled]{opacity:.5;cursor:wait}\
.rd-pill{font:700 12.5px system-ui;padding:5px 11px;border-radius:99px;color:#fff}\
.rd-row{border:1px solid var(--border,#e6e6ec);border-radius:12px;margin:8px 0;overflow:hidden}\
.rd-rh{all:unset;box-sizing:border-box;display:flex;gap:10px;align-items:center;width:100%;padding:11px 14px;cursor:pointer;font:600 13.5px var(--font,system-ui);color:var(--ink,#111)}\
.rd-dot{flex:none;width:10px;height:10px;border-radius:50%}.rd-nm{flex:1;overflow-wrap:anywhere}\
.rd-det{display:none;padding:2px 14px 12px 34px;font-size:13px;line-height:1.5;color:var(--ink,#111)}.rd-row.open .rd-det{display:block}\
.rd-ck{margin:3px 0;overflow-wrap:anywhere}.rd-sv{font-size:13px;margin:4px 0;overflow-wrap:anywhere}';
  function draw() {
    bodyEl.replaceChildren();
    var d = S.data, pad = h('div', { class: 'rd-body-in' });
    var run = h('button', { type: 'button', class: 'rd-btn', text: (d && d.running) ? 'Checking…' : 'Check all clients now', onclick: runAll });
    if (S.busy || (d && d.running)) run.disabled = true;
    var bar = h('div', { class: 'rd-bar' }, run);
    if (d && d.counts) {
      [['ok', 'ready'], ['warn', 'need attention'], ['fail', 'not ready']].forEach(function (p) {
        var s = h('span', { class: 'rd-pill', text: d.counts[p[0]] + ' ' + p[1] }); s.style.background = COL[p[0]]; bar.appendChild(s);
      });
      if (d.ts) bar.appendChild(h('small', { text: 'Last full check: ' + new Date(d.ts * 1000).toLocaleString() }));
      if (d.running && d.progress && d.progress.total) bar.appendChild(h('small', { text: d.progress.done + ' / ' + d.progress.total + ' done' }));
    }
    pad.appendChild(bar);
    if (S.err) pad.appendChild(h('p', { text: S.err, style: 'color:#dc2626' }));
    if (d) {
      pad.appendChild(h('b', { text: 'This server', style: 'font-size:13px' }));
      (d.server || []).forEach(function (c) { var l = h('div', { class: 'rd-sv' }, h('span', { text: ICO[c.status] + ' ', style: 'color:' + COL[c.status] + ';font-weight:700' }), c.text); pad.appendChild(l); });
      pad.appendChild(h('b', { text: 'Clients (worst first)', style: 'font-size:13px;display:block;margin-top:14px' }));
      if (!(d.clients || []).length) pad.appendChild(h('p', { text: 'No results yet - press "Check all clients now".', style: 'font-size:13px;color:var(--muted,#667)' }));
      (d.clients || []).forEach(function (c) {
        var row = h('div', { class: 'rd-row' });
        var bad = (c.checks || []).filter(function (x) { return x.status !== 'ok'; }).length;
        var hd = h('button', { type: 'button', class: 'rd-rh', onclick: function () { row.classList.toggle('open'); } },
          h('span', { class: 'rd-dot', style: 'background:' + COL[c.level] }), h('span', { class: 'rd-nm', text: (c.name || c.prefix) + '  (' + c.prefix + ')' }),
          h('small', { text: bad ? bad + ' point' + (bad > 1 ? 's' : '') + ' to look at' : 'all good' }));
        var det = h('div', { class: 'rd-det' });
        (c.checks || []).forEach(function (x) { det.appendChild(h('div', { class: 'rd-ck' }, h('span', { text: ICO[x.status] + ' ', style: 'color:' + COL[x.status] + ';font-weight:700' }), x.text)); });
        det.appendChild(h('button', { type: 'button', class: 'rd-btn', text: 'Re-check this client', style: 'margin-top:8px;padding:7px 12px', onclick: function () { runOne(c.prefix); } }));
        row.append(hd, det); pad.appendChild(row);
      });
    }
    bodyEl.appendChild(pad);
    if (d && d.counts) { badge.textContent = d.counts.fail ? d.counts.fail + ' not ready' : (d.counts.warn ? d.counts.warn + ' to review' : (d.clients && d.clients.length ? 'All ready' : 'Check')); }
    if (subEl && d) subEl.textContent = 'Is each client able to answer from its own database?';
  }
  function load() { return api('/admin/readiness').then(function (j) { S.data = j; S.err = ''; draw(); if (j.running) poll(); }).catch(function (e) { S.err = e.message; draw(); }); }
  function poll() { clearTimeout(S.timer); S.timer = setTimeout(load, 2500); }
  function runAll() { S.busy = true; draw(); api('/admin/readiness/run', { method: 'POST' }).then(function () { S.busy = false; load(); poll(); }).catch(function (e) { S.busy = false; S.err = e.message; draw(); }); }
  function runOne(p) { api('/admin/readiness/run?client=' + encodeURIComponent(p), { method: 'POST' }).then(function () { load(); poll(); }).catch(function (e) { S.err = e.message; draw(); }); }
  function toggle() { S.open = !S.open; root.classList.toggle('open', S.open); if (S.open) { draw(); load(); } }
  function mount() {
    if (document.getElementById('rdCard')) return;
    var grid = document.querySelector('#settingsPage .settings-grid'); if (!grid) return;
    document.head.appendChild(h('style', { id: 'rd-style', text: CSS }));
    badge = h('span', { class: 'rd-badge', text: 'Check' }); subEl = h('small', { text: 'Is each client able to answer from its own database?' });
    var head = h('button', { type: 'button', class: 'rd-head', 'aria-expanded': 'false' }, h('span', { class: 'rd-ico', text: '🩺' }), h('span', { class: 'rd-title' }, h('b', { text: 'Client Readiness' }), subEl), badge);
    head.addEventListener('click', toggle);
    bodyEl = h('div', { class: 'rd-body' });
    root = h('div', { class: 'settings-section rd-card', id: 'rdCard' }, head, bodyEl);
    grid.appendChild(root);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', mount); else mount();
})();
