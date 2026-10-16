/* Admin > Settings > "Scheduled Reports" card (additive; no other admin code is touched).
   Collapsed label card -> click to expand -> 1) which client  2) Email / WhatsApp / both  3) which collections + which basis
   (daily / weekly / monthly) and send time. Lists existing schedules with Preview / Send now / Pause / Edit / Delete.
   All text from the server is inserted with textContent. */
(function () {
  'use strict';
  var WD = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];
  var S = { open: false, loaded: false, data: null, editing: null, form: null, busy: false };

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
    var e = document.createElement(tag), i = 2;
    attrs = attrs || {};
    Object.keys(attrs).forEach(function (k) {
      if (k === 'class') e.className = attrs[k];
      else if (k === 'text') e.textContent = attrs[k];
      else if (k.slice(0, 2) === 'on') e.addEventListener(k.slice(2), attrs[k]);
      else if (attrs[k] !== false && attrs[k] != null) e.setAttribute(k, attrs[k] === true ? '' : attrs[k]);
    });
    for (; i < arguments.length; i++) { var c = arguments[i]; if (c == null || c === false) continue; e.appendChild(typeof c === 'string' ? document.createTextNode(c) : c); }
    return e;
  }

  var CSS = '\
.rs-card{grid-column:1/-1;padding:0!important;overflow:hidden;min-width:0;max-width:100%}.rs-card *{min-width:0}.rs-seg{max-width:100%}.rs-sum{overflow-wrap:anywhere}@media(max-width:600px){.rs-pad{padding:4px 14px 20px}.rs-head{padding:16px 14px}.rs-secs{grid-template-columns:minmax(0,1fr)}.rs-seg button{padding:7px 12px}}\
.rs-head{all:unset;box-sizing:border-box;display:flex;align-items:center;gap:14px;width:100%;padding:20px 22px;cursor:pointer}\
.rs-head:focus-visible{outline:2px solid var(--primary,#6a5cf6);outline-offset:-2px;border-radius:12px}\
.rs-ico{flex:none;width:42px;height:42px;border-radius:12px;display:grid;place-items:center;font-size:20px;background:linear-gradient(135deg,rgba(124,108,255,.22),rgba(34,211,238,.18));box-shadow:inset 0 0 0 1px rgba(124,108,255,.3)}\
.rs-title{flex:1;min-width:0}.rs-title b{display:block;font:650 15px var(--font,system-ui);color:var(--ink,#111);letter-spacing:-.01em}\
.rs-title small{display:block;margin-top:2px;font-size:12.5px;color:var(--muted,#667);overflow-wrap:anywhere}\
.rs-badge{flex:none;font-size:12px;font-weight:700;padding:4px 10px;border-radius:99px;background:var(--accent-soft,#eeeaff);color:var(--accent-ink,#4a3dd1)}\
.rs-chev{flex:none;width:22px;height:22px;transition:transform .35s cubic-bezier(.2,.7,.2,1);color:var(--muted,#667)}\
.rs-card.open .rs-chev{transform:rotate(180deg)}\
.rs-body{display:grid;grid-template-rows:0fr;transition:grid-template-rows .4s cubic-bezier(.2,.7,.2,1)}\
.rs-card.open .rs-body{grid-template-rows:1fr}\
.rs-inner{overflow:hidden;min-height:0}\
.rs-pad{padding:4px 22px 24px;border-top:1px solid var(--border,#e6e6ec)}\
.rs-grid{display:grid;grid-template-columns:minmax(0,1.05fr) minmax(0,1fr);gap:26px;margin-top:20px}\
@media(max-width:1100px){.rs-grid{grid-template-columns:minmax(0,1fr)}}\
.rs-step{margin-bottom:20px}.rs-step>label.rs-lab{display:flex;align-items:center;gap:10px;font:620 13.5px var(--font,system-ui);color:var(--ink,#111);margin-bottom:10px}\
.rs-n{flex:none;width:22px;height:22px;border-radius:50%;display:grid;place-items:center;font-size:12px;font-weight:700;color:#fff;background:linear-gradient(135deg,#7c6cff,#22d3ee)}\
.rs-in,.rs-sel{width:100%;box-sizing:border-box;height:40px;padding:0 12px;border:1px solid var(--border-strong,#d4d4dd);border-radius:10px;background:var(--surface,#fff);color:var(--ink,#111);font:inherit;font-size:14px}\
.rs-sel{background:var(--surface,#fff)!important;color:var(--ink,#111)!important;color-scheme:inherit}.rs-sel option{background:var(--surface,#fff);color:var(--ink,#111)}\
.rs-in:focus,.rs-sel:focus{outline:0;border-color:var(--primary,#6a5cf6);box-shadow:0 0 0 3px var(--ring,rgba(106,92,246,.28))}\
.rs-chips{display:flex;flex-wrap:wrap;gap:10px}\
.rs-chip{display:inline-flex;align-items:center;gap:8px;padding:9px 14px;border:1px solid var(--border-strong,#d4d4dd);border-radius:12px;cursor:pointer;font-size:13.5px;font-weight:550;color:var(--text,#333);background:var(--surface,#fff);user-select:none;transition:all .2s}\
.rs-chip input{position:absolute;opacity:0;pointer-events:none}\
.rs-chip:hover{border-color:var(--primary,#6a5cf6)}\
.rs-chip.on{background:var(--accent-soft,#eeeaff);border-color:var(--primary,#6a5cf6);color:var(--accent-ink,#4a3dd1);box-shadow:0 6px 18px -8px rgba(124,108,255,.6)}\
.rs-chip:focus-within{box-shadow:0 0 0 3px var(--ring,rgba(106,92,246,.28))}\
.rs-secs{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:8px}\
.rs-secs .rs-chip{border-radius:10px;padding:8px 12px;font-size:13px;white-space:normal;line-height:1.3}\
.rs-seg{display:inline-flex;padding:4px;gap:4px;border:1px solid var(--border-strong,#d4d4dd);border-radius:12px;background:var(--surface-2,#f3f3f6);flex-wrap:wrap}\
.rs-seg button{all:unset;cursor:pointer;padding:7px 16px;border-radius:9px;font-size:13px;font-weight:600;color:var(--muted,#667);transition:all .2s}\
.rs-seg button.on{background:var(--surface,#fff);color:var(--ink,#111);box-shadow:0 2px 8px rgba(0,0,0,.12)}\
.rs-row{display:flex;gap:12px;flex-wrap:wrap;margin-top:12px}.rs-row>div{flex:1;min-width:140px}\
.rs-row small.rs-cap{display:block;margin-bottom:5px;font-size:11.5px;letter-spacing:.06em;text-transform:uppercase;color:var(--muted,#667);font-weight:650}\
.rs-sum{margin-top:12px;padding:10px 12px;border-radius:10px;font-size:13px;background:var(--surface-2,#f3f3f6);color:var(--text,#333);border:1px dashed var(--border-strong,#d4d4dd)}\
.rs-warn{margin-top:8px;font-size:12.5px;color:#b45309;background:rgba(245,158,11,.12);border:1px solid rgba(245,158,11,.35);padding:8px 10px;border-radius:9px;overflow-wrap:anywhere}\
.rs-hint{margin-top:6px;font-size:12px;color:var(--muted,#667);overflow-wrap:anywhere}\
.rs-act{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-top:6px}\
.rs-btn{all:unset;box-sizing:border-box;cursor:pointer;padding:9px 16px;border-radius:10px;font-size:13px;font-weight:650;border:1px solid var(--border-strong,#d4d4dd);color:var(--text,#333);background:var(--surface,#fff);transition:transform .2s,border-color .2s;white-space:nowrap}\
.rs-btn:hover{transform:translateY(-1px);border-color:var(--primary,#6a5cf6)}.rs-btn:focus-visible{outline:2px solid var(--primary,#6a5cf6);outline-offset:2px}\
.rs-btn.pri{border:0;color:#fff;background:linear-gradient(120deg,#7c6cff,#22d3ee);box-shadow:0 8px 22px -8px rgba(124,108,255,.8)}\
.rs-btn.sm{padding:6px 11px;font-size:12px}.rs-btn.dng:hover{border-color:#dc2626;color:#dc2626}.rs-btn[disabled]{opacity:.55;cursor:wait}\
.rs-msg{font-size:13px;font-weight:600;overflow-wrap:anywhere}.rs-msg.err{color:#dc2626}.rs-msg.ok{color:#16a34a}\
.rs-list h4{margin:0 0 10px;font:650 13.5px var(--font,system-ui);color:var(--ink,#111)}\
.rs-item{border:1px solid var(--border,#e6e6ec);border-radius:14px;padding:14px;margin-bottom:12px;background:var(--surface,#fff)}\
.rs-item.off{opacity:.65}\
.rs-item-top{display:flex;gap:10px;align-items:flex-start;flex-wrap:wrap}.rs-item-top b{flex:1;min-width:0;overflow-wrap:anywhere;font-size:14px;color:var(--ink,#111)}\
.rs-pill{flex:none;font-size:11.5px;font-weight:700;padding:3px 9px;border-radius:99px;background:var(--surface-3,#ececf1);color:var(--text,#333)}\
.rs-pill.ok{background:rgba(22,163,74,.14);color:#15803d}.rs-pill.bad{background:rgba(220,38,38,.14);color:#b91c1c}.rs-pill.pause{background:rgba(245,158,11,.16);color:#b45309}\
.rs-meta{margin:6px 0 10px;font-size:12.5px;color:var(--muted,#667);line-height:1.55;overflow-wrap:anywhere}\
.rs-item-act{display:flex;gap:8px;flex-wrap:wrap}\
.rs-pre{margin-top:10px;white-space:pre-wrap;overflow-wrap:anywhere;font:12.5px/1.55 var(--mono,monospace);background:var(--surface-2,#f3f3f6);border:1px solid var(--border,#e6e6ec);border-radius:10px;padding:12px;max-height:260px;overflow:auto;color:var(--text,#333)}\
.rs-empty{padding:18px;text-align:center;border:1px dashed var(--border-strong,#d4d4dd);border-radius:14px;color:var(--muted,#667);font-size:13px}';

  function chev() {
    var ns = 'http://www.w3.org/2000/svg', s = document.createElementNS(ns, 'svg');
    s.setAttribute('viewBox', '0 0 24 24'); s.setAttribute('class', 'rs-chev'); s.setAttribute('fill', 'none'); s.setAttribute('stroke', 'currentColor'); s.setAttribute('stroke-width', '2.2'); s.setAttribute('stroke-linecap', 'round'); s.setAttribute('stroke-linejoin', 'round');
    var p = document.createElementNS(ns, 'path'); p.setAttribute('d', 'M6 9l6 6 6-6'); s.appendChild(p); return s;
  }

  function blank() { return { client: '', channels: ['email'], email_to: '', whatsapp_to: '', sections: ['total', 'mode'], frequency: 'daily', send_time: '08:00', weekday: 0, month_day: 1 }; }
  function basis(f) {
    var t = f.send_time || '08:00';
    if (f.frequency === 'weekly') return 'Every ' + WD[f.weekday] + ' at ' + t + ' - covers the previous 7 days';
    if (f.frequency === 'monthly') return 'On day ' + f.month_day + ' of every month at ' + t + ' - covers the previous month';
    return 'Every day at ' + t + ' - covers yesterday';
  }

  var root, bodyEl, badge, subEl;

  function chip(label, on, onToggle, name) {
    var i = h('input', { type: 'checkbox', checked: on ? '' : null, name: name || '' });
    i.checked = on;
    var l = h('label', { class: 'rs-chip' + (on ? ' on' : '') }, i, label);
    i.addEventListener('change', function () { l.classList.toggle('on', i.checked); onToggle(i.checked); });
    return l;
  }

  function renderForm() {
    var f = S.form, d = S.data, rdy = d.channels_ready;
    var wrap = h('div', { class: 'rs-form' });
    wrap.appendChild(h('h4', { text: S.editing ? 'Edit schedule' : 'New schedule', style: 'margin:0 0 14px;font:650 13.5px var(--font,system-ui);color:var(--ink,#111)' }));

    var sel = h('select', { class: 'rs-sel', 'aria-label': 'Client' }, h('option', { value: '', text: 'Choose a client...' }));
    d.clients.forEach(function (c) { var o = h('option', { value: c.code, text: c.name + ' (' + c.code + ')' }); if (c.code === f.client) o.selected = true; sel.appendChild(o); });
    sel.addEventListener('change', function () { f.client = sel.value; });
    wrap.appendChild(h('div', { class: 'rs-step' }, h('label', { class: 'rs-lab' }, h('span', { class: 'rs-n', text: '1' }), 'Which client?'), sel));

    var chW = h('div', { class: 'rs-chips' }), recip = h('div');
    function drawRecip() {
      recip.replaceChildren();
      if (f.channels.indexOf('email') >= 0) {
        var e = h('input', { class: 'rs-in', type: 'text', placeholder: 'owner@hospital.com, accounts@hospital.com', value: f.email_to, 'aria-label': 'Email recipients', style: 'margin-top:10px' });
        e.addEventListener('input', function () { f.email_to = e.value; }); recip.appendChild(e);
        if (!rdy.email) recip.appendChild(h('div', { class: 'rs-warn', text: 'Email is not set up on this server yet (Settings > SMTP). Reports will fail until it is.' }));
      }
      if (f.channels.indexOf('whatsapp') >= 0) {
        var w = h('input', { class: 'rs-in', type: 'text', placeholder: '+919876543210, +919812345678', value: f.whatsapp_to, 'aria-label': 'WhatsApp numbers', style: 'margin-top:10px' });
        w.addEventListener('input', function () { f.whatsapp_to = w.value; }); recip.appendChild(w);
        recip.appendChild(h('div', { class: 'rs-hint', text: 'Use the country code. WhatsApp delivers free text only to people who messaged you in the last 24 h - for everyone else the server needs an approved template (PINNACLE_WA_TEMPLATE_ID).' }));
        if (!rdy.whatsapp) recip.appendChild(h('div', { class: 'rs-warn', text: 'WhatsApp (Pinnacle) is not set up on this server yet - the 3 PINNACLE_WA_* settings are missing. Reports will fail until it is.' }));
      }
    }
    function tog(ch) { return function (on) { var i = f.channels.indexOf(ch); if (on && i < 0) f.channels.push(ch); if (!on && i >= 0) f.channels.splice(i, 1); drawRecip(); }; }
    chW.appendChild(chip('Email', f.channels.indexOf('email') >= 0, tog('email'), 'ch'));
    chW.appendChild(chip('WhatsApp', f.channels.indexOf('whatsapp') >= 0, tog('whatsapp'), 'ch'));
    drawRecip();
    wrap.appendChild(h('div', { class: 'rs-step' }, h('label', { class: 'rs-lab' }, h('span', { class: 'rs-n', text: '2' }), 'Send via (pick one or both)'), chW, recip));

    var secs = h('div', { class: 'rs-secs' });
    d.sections.forEach(function (s) {
      secs.appendChild(chip(s.label, f.sections.indexOf(s.key) >= 0, function (on) { var i = f.sections.indexOf(s.key); if (on && i < 0) f.sections.push(s.key); if (!on && i >= 0) f.sections.splice(i, 1); }, 'sec'));
    });
    var sum = h('div', { class: 'rs-sum', text: basis(f) });
    var seg = h('div', { class: 'rs-seg', role: 'group', 'aria-label': 'Basis' }), extra = h('div', { class: 'rs-row' });
    function drawExtra() {
      extra.replaceChildren();
      var t = h('input', { class: 'rs-in', type: 'time', value: f.send_time, 'aria-label': 'Send time' });
      t.addEventListener('input', function () { f.send_time = t.value || '08:00'; sum.textContent = basis(f); });
      if (f.frequency === 'weekly') {
        var w = h('select', { class: 'rs-sel', 'aria-label': 'Weekday' }); WD.forEach(function (n, i) { var o = h('option', { value: i, text: n }); if (i === +f.weekday) o.selected = true; w.appendChild(o); });
        w.addEventListener('change', function () { f.weekday = +w.value; sum.textContent = basis(f); });
        extra.appendChild(h('div', null, h('small', { class: 'rs-cap', text: 'Day' }), w));
      }
      if (f.frequency === 'monthly') {
        var m = h('select', { class: 'rs-sel', 'aria-label': 'Day of month' }); for (var i = 1; i <= 28; i++) { var o = h('option', { value: i, text: String(i) }); if (i === +f.month_day) o.selected = true; m.appendChild(o); }
        m.addEventListener('change', function () { f.month_day = +m.value; sum.textContent = basis(f); });
        extra.appendChild(h('div', null, h('small', { class: 'rs-cap', text: 'Day of month' }), m));
      }
      extra.appendChild(h('div', null, h('small', { class: 'rs-cap', text: 'Send at (IST)' }), t));
      sum.textContent = basis(f);
    }
    function drawSeg() {
      seg.replaceChildren();
      [['daily', 'Daily'], ['weekly', 'Weekly'], ['monthly', 'Monthly']].forEach(function (p) {
        var b = h('button', { type: 'button', class: f.frequency === p[0] ? 'on' : '', text: p[1], 'aria-pressed': f.frequency === p[0] ? 'true' : 'false' });
        b.addEventListener('click', function () { f.frequency = p[0]; drawSeg(); drawExtra(); }); seg.appendChild(b);
      });
    }
    drawSeg(); drawExtra();
    wrap.appendChild(h('div', { class: 'rs-step' }, h('label', { class: 'rs-lab' }, h('span', { class: 'rs-n', text: '3' }), 'What to include, and on which basis?'),
      secs, h('div', { style: 'margin-top:14px' }, seg), extra, sum));

    var msg = h('span', { class: 'rs-msg' });
    var save = h('button', { type: 'button', class: 'rs-btn pri', text: S.editing ? 'Save changes' : 'Create schedule' });
    save.addEventListener('click', function () {
      save.disabled = true; msg.className = 'rs-msg'; msg.textContent = 'Saving...';
      var body = { client: f.client, channels: f.channels, email_to: f.email_to, whatsapp_to: f.whatsapp_to, sections: f.sections, frequency: f.frequency, send_time: f.send_time, weekday: +f.weekday, month_day: +f.month_day };
      api(S.editing ? '/admin/report-schedules/' + S.editing : '/admin/report-schedules', { method: S.editing ? 'PUT' : 'POST', body: JSON.stringify(body) })
        .then(function (j) { if (j.status !== 'success') throw new Error(j.message || 'Could not save.'); S.editing = null; S.form = blank(); return load(true); })
        .catch(function (e) { msg.className = 'rs-msg err'; msg.textContent = e.message; save.disabled = false; });
    });
    var act = h('div', { class: 'rs-act' }, save);
    if (S.editing) { var cn = h('button', { type: 'button', class: 'rs-btn', text: 'Cancel' }); cn.addEventListener('click', function () { S.editing = null; S.form = blank(); draw(); }); act.appendChild(cn); }
    act.appendChild(msg);
    wrap.appendChild(act);
    return wrap;
  }

  function ago(ts) {
    if (!ts) return 'never';
    var s = Math.max(0, Date.now() / 1000 - ts);
    if (s < 90) return 'just now'; if (s < 5400) return Math.round(s / 60) + ' min ago'; if (s < 129600) return Math.round(s / 3600) + ' h ago';
    return new Date(ts * 1000).toLocaleDateString();
  }

  function renderItem(s) {
    var d = S.data, item = h('div', { class: 'rs-item' + (s.enabled ? '' : ' off') });
    var st = !s.enabled ? ['Paused', 'pause'] : (s.last_status === 'failed' ? ['Last run failed', 'bad'] : (s.last_status === 'sent' ? ['Last sent ' + ago(s.last_run_ts), 'ok'] : ['Not sent yet', '']));
    item.appendChild(h('div', { class: 'rs-item-top' }, h('b', { text: (s.hospital || s.client) + ' (' + s.client + ')' }), h('span', { class: 'rs-pill ' + st[1], text: st[0] })));
    var names = s.sections.map(function (k) { var x = d.sections.filter(function (q) { return q.key === k; })[0]; return x ? x.label : k; });
    item.appendChild(h('div', { class: 'rs-meta' },
      s.basis_text, h('br'), (s.channels.map(function (c) { return c === 'email' ? 'Email: ' + s.email_to.join(', ') : 'WhatsApp: ' + s.whatsapp_to.join(', '); }).join('  |  ')), h('br'),
      'Includes: ' + names.join(', ')));
    if (s.last_status === 'failed' && s.last_detail) item.appendChild(h('div', { class: 'rs-warn', text: s.last_detail }));
    var out = h('div'), msg = h('span', { class: 'rs-msg' });
    function run(label, path, btn, showText) {
      btn.disabled = true; msg.className = 'rs-msg'; msg.textContent = label; out.replaceChildren();
      api(path, { method: 'POST' }).then(function (j) {
        msg.className = 'rs-msg ' + (j.status === 'success' ? 'ok' : 'err'); msg.textContent = j.message || (j.status === 'success' ? 'Done.' : 'Failed.');
        if (showText && j.text) out.appendChild(h('div', { class: 'rs-pre', text: j.text }));
        btn.disabled = false; if (!showText) load(true, true);
      }).catch(function (e) { msg.className = 'rs-msg err'; msg.textContent = e.message; btn.disabled = false; });
    }
    var pv = h('button', { type: 'button', class: 'rs-btn sm', text: 'Preview' });
    pv.addEventListener('click', function () { run('Building the report from live data - this can take up to a minute...', '/admin/report-schedules/' + s.id + '/preview', pv, true); });
    var sn = h('button', { type: 'button', class: 'rs-btn sm', text: 'Send now' });
    sn.addEventListener('click', function () { if (confirm('Send this report now to the saved recipients?')) run('Building and sending...', '/admin/report-schedules/' + s.id + '/run-now', sn, false); });
    var pz = h('button', { type: 'button', class: 'rs-btn sm', text: s.enabled ? 'Pause' : 'Resume' });
    pz.addEventListener('click', function () { api('/admin/report-schedules/' + s.id + '/toggle', { method: 'POST' }).then(function () { load(true, true); }).catch(function (e) { msg.className = 'rs-msg err'; msg.textContent = e.message; }); });
    var ed = h('button', { type: 'button', class: 'rs-btn sm', text: 'Edit' });
    ed.addEventListener('click', function () {
      S.editing = s.id; S.form = { client: s.client, channels: s.channels.slice(), email_to: s.email_to.join(', '), whatsapp_to: s.whatsapp_to.join(', '), sections: s.sections.slice(), frequency: s.frequency, send_time: s.send_time, weekday: s.weekday, month_day: s.month_day };
      draw(); root.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    });
    var dl = h('button', { type: 'button', class: 'rs-btn sm dng', text: 'Delete' });
    dl.addEventListener('click', function () { if (confirm('Delete this scheduled report?')) api('/admin/report-schedules/' + s.id, { method: 'DELETE' }).then(function () { load(true, true); }).catch(function (e) { msg.className = 'rs-msg err'; msg.textContent = e.message; }); });
    item.appendChild(h('div', { class: 'rs-item-act' }, pv, sn, pz, ed, dl, msg));
    item.appendChild(out);
    return item;
  }

  function draw() {
    if (!bodyEl) return;
    bodyEl.replaceChildren();
    var d = S.data;
    if (!d) { bodyEl.appendChild(h('div', { class: 'rs-pad' }, h('div', { class: 'rs-empty', text: S.err || 'Loading...' }))); return; }
    badge.textContent = d.schedules.length + (d.schedules.length === 1 ? ' schedule' : ' schedules');
    subEl.textContent = d.schedules.length ? d.schedules.filter(function (s) { return s.enabled; }).length + ' active - collection summaries by Email / WhatsApp' : 'Send collection summaries to owners by Email / WhatsApp';
    var list = h('div', { class: 'rs-list' }, h('h4', { text: 'Your schedules' }));
    if (!d.schedules.length) list.appendChild(h('div', { class: 'rs-empty', text: 'No scheduled reports yet. Fill in the 3 steps and press "Create schedule".' }));
    d.schedules.forEach(function (s) { list.appendChild(renderItem(s)); });
    bodyEl.appendChild(h('div', { class: 'rs-pad' }, h('div', { class: 'rs-grid' }, renderForm(), list)));
  }

  function load(force, keepForm) {
    if (S.loaded && !force) return Promise.resolve();
    return api('/admin/report-schedules').then(function (j) {
      S.data = j; S.loaded = true; S.err = ''; if (!S.form) S.form = blank();
      if (!keepForm && !S.editing) S.form = S.form || blank();
      draw();
    }).catch(function (e) { S.err = e.message; draw(); });
  }

  function toggle() {
    S.open = !S.open; root.classList.toggle('open', S.open);
    root.querySelector('.rs-head').setAttribute('aria-expanded', S.open ? 'true' : 'false');
    if (S.open) { draw(); load(false); }
  }

  function mount() {
    if (document.getElementById('rsCard')) return;
    var grid = document.querySelector('#settingsPage .settings-grid');
    if (!grid) return;
    document.head.appendChild(h('style', { id: 'rs-style', text: CSS }));
    badge = h('span', { class: 'rs-badge', text: 'Reports' }); subEl = h('small', { text: 'Send collection summaries to owners by Email / WhatsApp' });
    var head = h('button', { type: 'button', class: 'rs-head', 'aria-expanded': 'false', 'aria-controls': 'rsBody' },
      h('span', { class: 'rs-ico', text: '⏰', 'aria-hidden': 'true' }), h('span', { class: 'rs-title' }, h('b', { text: 'Scheduled Reports' }), subEl), badge, chev());
    head.addEventListener('click', toggle);
    bodyEl = h('div', { class: 'rs-inner', id: 'rsBody' });
    root = h('div', { class: 'settings-section rs-card', id: 'rsCard' }, head, h('div', { class: 'rs-body' }, bodyEl));
    grid.appendChild(root);
    if (location.hash === '#scheduled-reports') toggle();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', mount); else mount();
})();
