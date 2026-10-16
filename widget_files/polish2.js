/* Sahasra widget - polish layer 2 (additive; load AFTER polish.js, last in <body>).
   Stop button + friendly retry while the AI works - clearer numbers in tables - plain-language "How was this calculated?" -
   small "Showing:" line when a follow-up was understood - accessibility helpers. Off switch: ?polish2=off */
(function () {
  'use strict';
  if (/[?&]polish2=off/.test(location.search)) return;
  function qs(s, r) { return (r || document).querySelector(s); }
  function qsa(s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); }

  /* ---------------- fetch wrapper: abort + friendly failure for POST .../ask(/stream) */
  var fetch1 = window.fetch, ctl = null, lastQ = '', FRIENDLY = "I couldn't reach the server. Please check your connection and try again.";
  function askBody(init) { try { return JSON.parse(init.body).question || ''; } catch (e) { return ''; } }
  window.fetch = function (input, init) {
    var url = typeof input === 'string' ? input : (input && input.url) || '', path = '';
    try { path = new URL(url, location.href).pathname; } catch (e) {}
    if (!/\/ask$/.test(path) || !init || String(init.method || 'GET').toUpperCase() !== 'POST') return fetch1.apply(this, arguments);
    ctl = new AbortController(); lastQ = askBody(init);
    var mine = ctl, init2 = Object.assign({}, init, { signal: mine.signal });
    return fetch1.call(this, input, init2).then(function (res) {
      var ct = res.headers.get('content-type') || '';
      if (!res.ok && ct.indexOf('json') < 0) throw new Error('http' + res.status);
      return res;
    }).catch(function (e) {
      var stopped = mine.signal.aborted;
      window.__sx_failed = stopped ? '' : lastQ;
      return new Response(JSON.stringify({ status: stopped ? 'stopped' : 'error',
        answer: stopped ? 'Stopped. You can ask again, or rephrase the question.' : FRIENDLY }), { status: 200, headers: { 'Content-Type': 'application/json' } });
    });
  };

  /* ---------------- stop button inside the typing bubble; retry chip after a failure */
  function addStop(el) {
    if (el.querySelector('.sx-stop')) return;
    var b = document.createElement('button'); b.type = 'button'; b.className = 'sx-stop'; b.textContent = 'Stop';
    b.setAttribute('aria-label', 'Stop this answer'); b.addEventListener('click', function () { try { ctl && ctl.abort(); } catch (e) {} });
    el.appendChild(b);
  }
  function addRetry(msgEl) {
    if (!window.__sx_failed || msgEl.querySelector('.sx-retry')) return;
    var q = window.__sx_failed; window.__sx_failed = '';
    var b = document.createElement('button'); b.type = 'button'; b.className = 'sx-retry'; b.textContent = '↻ Try again';
    b.addEventListener('click', function () { var i = qs('#msg'); if (!i) return; b.disabled = true; i.value = q; try { window.handleSend(); } catch (e) {} });
    msgEl.appendChild(b);
  }
  var chat = qs('#chat');
  if (chat) {
    new MutationObserver(function (muts) {
      muts.forEach(function (m) {
        m.addedNodes.forEach(function (n) {
          if (!n.classList) return;
          if (n.classList.contains('typing-indicator')) addStop(n);
          else if (n.classList.contains('bot') && (n.textContent || '').indexOf(FRIENDLY) >= 0) addRetry(n);
          if (n.classList.contains('bot') && n.querySelector) enhance(n);
        });
      });
    }).observe(chat, { childList: true });
  }

  /* ---------------- clearer numbers in tables */
  var NUM = /^[\s₹$€£+\-−(]*\d[\d,]*(\.\d+)?\s*(%|₹|cr|lakh|k|m)?\)?\s*$/i;
  function enhance(msg) {
    qsa('table', msg).forEach(function (t) {
      if (t.dataset.sx) return; t.dataset.sx = '1';
      var rows = qsa('tr', t), cols = rows[0] ? rows[0].children.length : 0;
      for (var c = 0; c < cols; c++) {
        var cells = rows.slice(1).map(function (r) { return r.children[c]; }).filter(Boolean);
        if (cells.length && cells.every(function (td) { return NUM.test((td.textContent || '').trim()) || !(td.textContent || '').trim(); })) {
          cells.forEach(function (td) { td.classList.add('sx-num'); }); if (rows[0].children[c]) rows[0].children[c].classList.add('sx-num');
        }
      }
    });
  }
  qsa('#chat .message.bot').forEach(enhance);

  /* ---------------- "Showing: ..." when a follow-up was rewritten by the server */
  var attach0 = window.attachAnswerActions;
  if (typeof attach0 === 'function') {
    window.attachAnswerActions = function (data) {
      var r = attach0.apply(this, arguments);
      try {
        if (data && data.understood_as) {
          var bots = qsa('#chat .message.bot'), last = bots[bots.length - 1];
          if (last && !last.querySelector('.sx-understood')) {
            var s = document.createElement('div'); s.className = 'sx-understood'; s.textContent = 'Showing: ' + data.understood_as; last.appendChild(s);
          }
        }
      } catch (e) {}
      return r;
    };
  }

  /* ---------------- plain-language "How was this calculated?" (no table names, no SQL) */
  function plainExplain(ex) {
    ex = ex || {};
    var d = qs('#sxExplain'); if (d) d.remove();
    var wrap = document.createElement('div'); wrap.id = 'sxExplain'; wrap.className = 'sx-modal'; wrap.setAttribute('role', 'dialog'); wrap.setAttribute('aria-modal', 'true'); wrap.setAttribute('aria-label', 'How was this calculated?');
    var box = document.createElement('div'); box.className = 'sx-box';
    var h = document.createElement('h3'); h.textContent = 'How was this calculated?'; box.appendChild(h);
    function line(t) { if (!t) return; var p = document.createElement('p'); p.textContent = t; box.appendChild(p); }
    line(ex.note);
    if (ex.periods && ex.periods.length) line('Period: ' + ex.periods.join(', '));
    line('Only your own hospital’s data was used, and nothing was changed.');
    var x = document.createElement('button'); x.type = 'button'; x.className = 'sx-close'; x.textContent = 'Got it';
    x.addEventListener('click', function () { wrap.remove(); }); box.appendChild(x);
    wrap.addEventListener('click', function (e) { if (e.target === wrap) wrap.remove(); });
    wrap.addEventListener('keydown', function (e) { if (e.key === 'Escape') wrap.remove(); });
    wrap.appendChild(box); document.body.appendChild(wrap); x.focus();
  }
  window.showExplainDialog = plainExplain;

  /* ---------------- accessibility helpers */
  qsa('button:not([aria-label]):not([title])').forEach(function (b) { if (!(b.textContent || '').trim()) b.setAttribute('aria-label', 'Button'); });
  var st = qs('#status'); if (st) { st.setAttribute('role', 'status'); st.setAttribute('aria-live', 'polite'); }
  /* ---------------- brand initial when a client has no logo image */
  function initial() {
    var logo = qs('.logo'), h1 = qs('.header-info h1'); if (!logo || !h1) return;
    if (logo.querySelector('img,svg') || logo.querySelector('.sx-initial')) return;
    var t = (h1.textContent || '').trim(); if (!t) return;
    var s = document.createElement('span'); s.className = 'sx-initial'; s.textContent = t.charAt(0).toUpperCase(); s.setAttribute('aria-hidden', 'true'); logo.appendChild(s);
  }
  initial(); var hd = qs('.header'); if (hd) new MutationObserver(initial).observe(hd, { childList: true, subtree: true, characterData: true });
})();

/* Device lock: "already logged in on another device" gets a button to log that device out */
(function () {
  'use strict';
  var base = '', code = '';
  try {
    var of = window.fetch;
    window.fetch = function (u, o) {
      try {
        var url = typeof u === 'string' ? u : (u && u.url) || '';
        if (o && typeof o.body === 'string' && o.body.indexOf('activation_code') > -1) {
          var j = JSON.parse(o.body); if (j.activation_code) { code = String(j.activation_code); base = new URL(url, location.href).origin; }
        }
      } catch (e) {}
      return of.apply(this, arguments);
    };
  } catch (e) {}
  var KEY = 'already logged in on another device';
  function scan() {
    var els = document.querySelectorAll('div,p,span');
    for (var i = 0; i < els.length; i++) {
      var el = els[i];
      if (el.getAttribute('data-sx-dev') || el.children.length > 3) continue;
      var own = Array.prototype.filter.call(el.childNodes, function (n) { return n.nodeType === 3; }).map(function (n) { return n.textContent; }).join(' ');
      if (own.toLowerCase().indexOf(KEY) < 0) continue;
      el.setAttribute('data-sx-dev', '1');
      var b = document.createElement('button'); b.type = 'button'; b.textContent = 'Log out the other device';
      b.style.cssText = 'display:block;margin:10px 0 2px;padding:9px 14px;border:0;border-radius:10px;background:var(--primary,#6a5cf6);color:#fff;font:600 13px system-ui;cursor:pointer';
      b.addEventListener('click', function () {
        if (!code) { b.textContent = 'Please sign in again'; return; }
        b.disabled = true; b.textContent = 'Logging out...';
        fetch((base || '') + '/release-device', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ activation_code: code }) })
          .then(function (r) { if (!r.ok) throw new Error(); b.textContent = 'Done - ask your question again'; })
          .catch(function () { b.disabled = false; b.textContent = 'Could not log out - try again'; });
      });
      el.appendChild(b);
    }
  }
  var t; new MutationObserver(function () { clearTimeout(t); t = setTimeout(scan, 150); }).observe(document.documentElement, { childList: true, subtree: true });
})();
