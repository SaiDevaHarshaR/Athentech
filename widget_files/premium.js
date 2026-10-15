/* Sahasra chat — premium layer v3.
   - Standalone page (opened directly, no client params): cinematic landing with a real 3D DNA helix (landing.js + three.js).
   - Embedded widget (iframe / white-label / ?client=...): compact glass chat with a 2D DNA helix backdrop.
   Dark/light toggle in both. Decorative only: never touches chat logic. ?premium=off disables; ?landing=off keeps chat-only. */
(function () {
  'use strict';
  var SRC = document.currentScript && document.currentScript.src, BASE = SRC ? SRC.replace(/[^\/]*$/, '') : '';
  try {
    var qs = new URLSearchParams(location.search), root = document.documentElement;
    if (qs.get('premium') === 'off') return;
    var reduce = window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches;
    var standalone = window.top === window.self && !qs.get('client') && !qs.get('label') && !qs.get('mode') && !qs.get('embedder') && qs.get('landing') === 'on'; /* landing page is opt-in; the widget is chat-only by default */

    /* ---------- theme + toggle ---------- */
    function storedTheme() { try { return localStorage.getItem('sahasra_pz_theme'); } catch (e) { return null; } }
    var theme = storedTheme() || (qs.get('theme') === 'light' ? 'light' : 'dark'); if (theme !== 'light') theme = 'dark';
    root.classList.add('pz'); root.setAttribute('data-pz-theme', theme);
    function isDark() { return root.getAttribute('data-pz-theme') !== 'light'; }
    function el(tag, cls, id) { var e = document.createElement(tag); if (cls) e.className = cls; if (id) e.id = id; return e; }
    var tg = el('button', 'pz-toggle'); tg.type = 'button';
    tg.innerHTML = '<svg class="sun" viewBox="0 0 24 24"><circle cx="12" cy="12" r="4.2"/><path d="M12 2.5v2.2M12 19.3v2.2M4.6 4.6l1.6 1.6M17.8 17.8l1.6 1.6M2.5 12h2.2M19.3 12h2.2M4.6 19.4l1.6-1.6M17.8 6.2l1.6-1.6"/></svg>' +
      '<svg class="moon" viewBox="0 0 24 24"><path d="M20.5 14.2A8.6 8.6 0 0 1 9.8 3.5a8.6 8.6 0 1 0 10.7 10.7z"/></svg>';
    window.__pzToggle = tg;
    function label() { tg.setAttribute('aria-label', isDark() ? 'Switch to light mode' : 'Switch to dark mode'); tg.title = tg.getAttribute('aria-label'); }
    var onTheme = function () {};
    function setTheme(t) { root.setAttribute('data-pz-theme', t); try { localStorage.setItem('sahasra_pz_theme', t); } catch (e) {} label(); onTheme(); }
    tg.addEventListener('click', function () {
      var next = isDark() ? 'light' : 'dark';
      if (document.startViewTransition && !reduce) {
        var r = tg.getBoundingClientRect(); root.style.setProperty('--vt-x', Math.round(r.left + r.width / 2) + 'px'); root.style.setProperty('--vt-y', Math.round(r.top + r.height / 2) + 'px');
        document.startViewTransition(function () { setTheme(next); });
      } else setTheme(next);
    });
    label();

    if (standalone && 'noModule' in HTMLScriptElement.prototype && BASE) {
      var im = el('script'); im.type = 'importmap'; im.textContent = JSON.stringify({ imports: { three: BASE + 'vendor/three/build/three.module.min.js' } }); document.head.appendChild(im);
      var css = el('link'); css.rel = 'stylesheet'; css.href = BASE + 'landing.css'; document.head.appendChild(css);
      import(BASE + 'landing.js').catch(function (e) { try { console.warn('[landing] falling back to chat-only', e); } catch (_) {} root.classList.remove('pz-land'); var l = document.getElementById('pzl'); if (l) l.remove(); startEmbedded(); });
      return;
    }
    startEmbedded();

    /* ====================== embedded / chat-only ====================== */
    function startEmbedded() {
      var host = document.body;
      var aurora = el('div', 'pz-aurora'), grid = el('div', 'pz-grid'), spot = el('div', 'pz-spot'), bg = el('canvas', '', 'pz-bg'), orb = el('canvas', '', 'pz-orb'), hero = el('div', 'pz-hero');
      var h = el('h2'), p = el('p');
      (function letters(text) {
        var i = 0, words = text.split(' '); words.forEach(function (word, wi) {
          var w = el('span', 'w'); word.split('').forEach(function (ch) { var l = el('span', 'l'); l.style.setProperty('--i', i++); l.textContent = ch; w.appendChild(l); });
          h.appendChild(w); if (wi < words.length - 1) { h.appendChild(document.createTextNode(' ')); i++; }
        }); h.setAttribute('aria-label', text);
      })('Ask your hospital data');
      p.textContent = 'Plain-English questions. Answers come only from your own records.';
      hero.appendChild(h); hero.appendChild(p);
      var layers = [aurora, grid, spot, bg, orb, hero];
      layers.slice().reverse().forEach(function (n) { n.setAttribute('aria-hidden', 'true'); host.insertBefore(n, host.firstChild); });
      var bx = bg.getContext('2d'), ox = orb.getContext('2d');
      if (!bx || !ox) { root.classList.remove('pz'); return; }
      var W = 0, H = 0, DPR = 1, accent = [124, 108, 255], teal = [45, 225, 194], mouse = { x: .5, y: .5, tx: .5, ty: .5 };
      function parseColor(s) {
        s = (s || '').trim(); var m = s.match(/^#([0-9a-f]{3}|[0-9a-f]{6})$/i);
        if (m) { var v = m[1]; if (v.length === 3) v = v.replace(/./g, '$&$&'); return [parseInt(v.slice(0, 2), 16), parseInt(v.slice(2, 4), 16), parseInt(v.slice(4, 6), 16)]; }
        m = s.match(/rgba?\(\s*(\d+)[\s,]+(\d+)[\s,]+(\d+)/i); return m ? [+m[1], +m[2], +m[3]] : null;
      }
      function readAccent() { var c = parseColor(getComputedStyle(root).getPropertyValue('--w-accent')); if (c) accent = c; }
      function rgba(c, a) { return 'rgba(' + c[0] + ',' + c[1] + ',' + c[2] + ',' + a + ')'; }
      function resize() {
        DPR = Math.min(window.devicePixelRatio || 1, 2); W = window.innerWidth; H = window.innerHeight;
        [bg, orb].forEach(function (c) { c.width = Math.round(W * DPR); c.height = Math.round(H * DPR); });
        bx.setTransform(DPR, 0, 0, DPR, 0, 0); ox.setTransform(DPR, 0, 0, DPR, 0, 0); initParticles();
      }
      var P = [];
      function initParticles() {
        var n = Math.round(Math.min(60, Math.max(18, (W * H) / 16000))); P = [];
        for (var i = 0; i < n; i++) P.push({ x: Math.random() * W, y: Math.random() * H, vx: (Math.random() - .5) * .22, vy: (Math.random() - .5) * .22, r: Math.random() * 1.4 + .5 });
      }
      function drawBg() {
        bx.clearRect(0, 0, W, H);
        var dark = isDark(), dot = dark ? teal : [20, 130, 120], line = dark ? accent : [60, 70, 150], link = Math.min(140, Math.max(80, W / 5));
        for (var i = 0; i < P.length; i++) {
          var a = P[i]; a.x += a.vx; a.y += a.vy;
          if (a.x < -10) a.x = W + 10; else if (a.x > W + 10) a.x = -10; if (a.y < -10) a.y = H + 10; else if (a.y > H + 10) a.y = -10;
          bx.fillStyle = rgba(dot, dark ? .55 : .45); bx.beginPath(); bx.arc(a.x, a.y, a.r, 0, 6.2832); bx.fill();
          for (var j = i + 1; j < P.length; j++) { var b = P[j], dx = a.x - b.x, dy = a.y - b.y, d = dx * dx + dy * dy;
            if (d < link * link) { bx.strokeStyle = rgba(line, (1 - Math.sqrt(d) / link) * (dark ? .28 : .22)); bx.lineWidth = .6; bx.beginPath(); bx.moveTo(a.x, a.y); bx.lineTo(b.x, b.y); bx.stroke(); } }
        }
      }

      /* 2D-projected DNA helix */
      var st = { talking: false, typing: false, energy: 0, spin: 0, t: 0 };
      function drawHelix(dt) {
        ox.clearRect(0, 0, W, H); var dark = isDark();
        st.energy += ((st.typing ? 1 : st.talking ? .22 : .06) - st.energy) * Math.min(1, dt * 3); st.spin += dt * (.5 + st.energy * 2.6); st.t += dt;
        mouse.x += (mouse.tx - mouse.x) * .06; mouse.y += (mouse.ty - mouse.y) * .06;
        var halfH = Math.max(90, Math.min(H * .27, 200)), Rr = Math.max(34, Math.min(W * .15, 66)), cx = W / 2 + (mouse.x - .5) * 24, cy = H * (st.talking ? .36 : .39), TURNS = 2.6, tilt = (mouse.y - .5) * .3;
        root.style.setProperty('--pz-hero-top', Math.round(cy + halfH + 26) + 'px');
        var strokeA = dark ? accent : [70, 60, 200], strokeB = dark ? teal : [14, 150, 130], core = dark ? [255, 255, 255] : [20, 26, 70];
        function pt(u, ph) { var a = u * TURNS * 6.2832 + st.spin + ph, z = Math.sin(a), sc = 1 + z * .28; return { x: cx + Math.cos(a) * Rr * sc, y: cy + (u - .5) * 2 * halfH + z * 6 * tilt, z: z, sc: sc }; }
        var SEG = 90;
        [0, Math.PI].forEach(function (ph, si) {
          var col = si ? strokeB : strokeA, prev = pt(0, ph);
          for (var i = 1; i <= SEG; i++) { var cur = pt(i / SEG, ph), a = .22 + (cur.z + 1) / 2 * .7;
            ox.strokeStyle = rgba(col, a * (1 + st.energy * .3)); ox.lineWidth = 1.2 + cur.sc * 1.5; ox.lineCap = 'round'; ox.shadowColor = rgba(col, .9); ox.shadowBlur = dark ? 10 + st.energy * 10 : 0;
            ox.beginPath(); ox.moveTo(prev.x, prev.y); ox.lineTo(cur.x, cur.y); ox.stroke(); prev = cur; }
        }); ox.shadowBlur = 0;
        var R = 24;
        for (var r = 0; r < R; r++) {
          var u = (r + .5) / R, A = pt(u, 0), B = pt(u, Math.PI), z = (A.z + B.z) / 2, g = ox.createLinearGradient(A.x, A.y, B.x, B.y);
          g.addColorStop(0, rgba(strokeA, .5)); g.addColorStop(1, rgba(strokeB, .5)); ox.strokeStyle = g; ox.lineWidth = 1.2; ox.globalAlpha = .35 + (z + 1) / 4 + st.energy * .2;
          ox.beginPath(); ox.moveTo(A.x, A.y); ox.lineTo(B.x, B.y); ox.stroke(); ox.globalAlpha = 1;
          [[A, strokeA], [B, strokeB]].forEach(function (n) { var q = n[0]; ox.fillStyle = rgba(n[1], .5 + (q.z + 1) / 2 * .5); ox.shadowColor = rgba(n[1], 1); ox.shadowBlur = dark ? 12 : 0; ox.beginPath(); ox.arc(q.x, q.y, 2.2 * q.sc + 1, 0, 6.2832); ox.fill();
            ox.shadowBlur = 0; ox.fillStyle = rgba(core, .85); ox.beginPath(); ox.arc(q.x, q.y, .9 * q.sc, 0, 6.2832); ox.fill(); });
        }
        for (var k = 0; k < 4; k++) { var u2 = (st.t * (.12 + st.energy * .5) + k / 4) % 1, q2 = pt(u2, k % 2 ? Math.PI : 0); ox.fillStyle = rgba(core, 1); ox.shadowColor = rgba(k % 2 ? strokeB : strokeA, 1); ox.shadowBlur = 16; ox.beginPath(); ox.arc(q2.x, q2.y, 3.2 * q2.sc, 0, 6.2832); ox.fill(); ox.shadowBlur = 0; }
      }

      var last = 0, raf = 0, running = false;
      function frame(ts) { raf = requestAnimationFrame(frame); var dt = Math.min(.05, (ts - last) / 1000 || .016); last = ts; drawBg(); drawHelix(dt); }
      function start() { if (running || reduce) return; running = true; last = performance.now(); raf = requestAnimationFrame(frame); }
      function stop() { running = false; cancelAnimationFrame(raf); }
      function still() { drawBg(); drawHelix(.016); }
      onTheme = function () { setTimeout(readAccent, 30); if (reduce) still(); };
      document.addEventListener('visibilitychange', function () { document.hidden ? stop() : start(); });
      window.addEventListener('resize', function () { resize(); if (reduce) still(); });
      window.addEventListener('pointermove', function (e) {
        mouse.tx = e.clientX / Math.max(1, W); mouse.ty = e.clientY / Math.max(1, H);
        root.style.setProperty('--pz-sx', e.clientX + 'px'); root.style.setProperty('--pz-sy', e.clientY + 'px');
        var b = e.target && e.target.closest && e.target.closest('.suggestions button, .wl-quick-actions button');
        if (b) { var r = b.getBoundingClientRect(); b.style.setProperty('--mx', (e.clientX - r.left) + 'px'); b.style.setProperty('--my', (e.clientY - r.top) + 'px'); }
      }, { passive: true });
      (function place() { var badge = document.getElementById('modeBadge'); if (badge && badge.parentNode) badge.parentNode.insertBefore(tg, badge.nextSibling); else setTimeout(place, 300); })();
      function sync() { var chat = document.getElementById('chat'); if (!chat) return; st.talking = !!chat.querySelector('.message.user'); st.typing = !!chat.querySelector('.typing-indicator'); root.classList.toggle('pz-talking', st.talking); }
      (function watch() {
        var chat = document.getElementById('chat'); if (!chat) { setTimeout(watch, 300); return; }
        new MutationObserver(function (muts) { muts.forEach(function (m) { m.addedNodes.forEach(function (n) { if (n.nodeType === 1 && n.classList && n.classList.contains('message') && !reduce) n.classList.add('pz-in'); }); }); sync(); }).observe(chat, { childList: true, subtree: true });
        sync();
      })();
      readAccent(); setInterval(readAccent, 2000); resize(); if (reduce) still(); else start();
    }
  } catch (e) { try { document.documentElement.classList.remove('pz'); } catch (_) {} }
})();
