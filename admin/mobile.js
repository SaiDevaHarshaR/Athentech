/* Sahasra Admin - phone behaviour: slide-in menu, bottom tabs, table cell labels, edge swipe. Off: ?mobile=off */
(function () {
  'use strict';
  if (/[?&]mobile=off/.test(location.search)) return;
  var $ = function (s, r) { return (r || document).querySelector(s); }, $$ = function (s, r) { return [].slice.call((r || document).querySelectorAll(s)); };
  var NS = 'http://www.w3.org/2000/svg';
  function svg(d) { var s = document.createElementNS(NS, 'svg'); s.setAttribute('viewBox', '0 0 24 24'); d.forEach(function (p) { var e = document.createElementNS(NS, 'path'); e.setAttribute('d', p); s.appendChild(e); }); return s; }
  var ICON = { menu: ['M4 7h16', 'M4 12h16', 'M4 17h16'], search: ['M21 21l-4.3-4.3', 'M11 18a7 7 0 1 0 0-14 7 7 0 0 0 0 14z'],
    dashboard: ['M4 4h7v9H4z', 'M13 4h7v5h-7z', 'M13 11h7v9h-7z', 'M4 15h7v5H4z'], licenses: ['M15 7a4 4 0 1 1-3.5 6L3 21v-3l2-2h2v-2h2l2.5-2.5', 'M16 8h.01'],
    institutions: ['M4 21V7l8-4 8 4v14', 'M9 21v-6h6v6', 'M9 10h.01M15 10h.01'], audit: ['M12 7v5l3 2', 'M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0z'], more: ['M5 12h.01', 'M12 12h.01', 'M19 12h.01'] };
  var mq = window.matchMedia('(max-width: 900px)');

  function setOpen(on) { document.body.classList.toggle('px-nav-open', !!on); var m = $('#pxMenu'); if (m) m.setAttribute('aria-expanded', on ? 'true' : 'false'); if (on) { var a = $('.sidebar .nav-item.active') || $('.sidebar .nav-item'); a && a.focus({ preventScroll: true }); } }

  function build() {
    var top = $('.topbar'); if (!top || $('#pxMenu')) return;
    var mb = document.createElement('button'); mb.id = 'pxMenu'; mb.type = 'button'; mb.setAttribute('aria-label', 'Open menu'); mb.setAttribute('aria-expanded', 'false'); mb.appendChild(svg(ICON.menu));
    mb.addEventListener('click', function () { setOpen(!document.body.classList.contains('px-nav-open')); });
    top.insertBefore(mb, top.firstChild);
    var sb = document.createElement('button'); sb.id = 'pxSearchBtn'; sb.type = 'button'; sb.setAttribute('aria-label', 'Search'); sb.appendChild(svg(ICON.search));
    sb.addEventListener('click', function () { if (window.__polish && window.__polish.openCmdk) window.__polish.openCmdk(); else document.dispatchEvent(new KeyboardEvent('keydown', { key: 'k', ctrlKey: true, bubbles: true })); });
    var prof = $('.admin-profile'); prof ? prof.insertBefore(sb, prof.firstChild) : top.appendChild(sb);
    var sc = document.createElement('div'); sc.id = 'pxScrim'; sc.addEventListener('click', function () { setOpen(false); }); (document.querySelector('.app') || document.body).appendChild(sc);   /* same stacking context as the sidebar */
    $$('.sidebar .nav-item').forEach(function (n) { n.addEventListener('click', function () { setOpen(false); }); });
    document.addEventListener('keydown', function (e) { if (e.key === 'Escape') setOpen(false); });

    var tabs = document.createElement('nav'); tabs.id = 'pxTabs'; tabs.setAttribute('aria-label', 'Main');
    [['dashboard', 'Home', 'dashboard'], ['licenses', 'Licenses', 'licenses'], ['institutions', 'Institutes', 'institutions'], ['audit', 'Audit', 'audit']].forEach(function (t) {
      var b = document.createElement('button'); b.type = 'button'; b.dataset.go = t[0]; b.appendChild(svg(ICON[t[2]])); b.appendChild(document.createTextNode(t[1]));
      b.addEventListener('click', function () { var n = $('.sidebar .nav-item[data-page="' + t[0] + '"]'); n && n.click(); }); tabs.appendChild(b);
    });
    var more = document.createElement('button'); more.type = 'button'; more.dataset.go = 'more'; more.appendChild(svg(ICON.more)); more.appendChild(document.createTextNode('More'));
    more.addEventListener('click', function () { setOpen(true); }); tabs.appendChild(more);
    document.body.appendChild(tabs);
    syncTabs();
    var nav = $('.sidebar .navigation'); if (nav) new MutationObserver(syncTabs).observe(nav, { attributes: true, subtree: true, attributeFilter: ['class'] });
  }
  function syncTabs() {
    var a = $('.sidebar .nav-item.active'), page = a && a.dataset.page, hit = false;
    $$('#pxTabs button').forEach(function (b) { var on = b.dataset.go === page; if (on) hit = true; b.classList.toggle('on', on); });
    var more = $('#pxTabs [data-go="more"]'); if (more && !hit && page) more.classList.add('on');
  }

  /* label every cell with its column header so the table can render as cards */
  function labelTable(t) {
    var heads = $$('thead th', t).map(function (th) { return th.textContent.trim(); });
    if (!heads.length) return;
    $$('tbody tr', t).forEach(function (tr) {
      var i = 0;
      $$(':scope > td', tr).forEach(function (td) {
        var span = +td.getAttribute('colspan') || 1;
        if (span === 1 && !td.hasAttribute('data-label')) td.setAttribute('data-label', heads[i] || '');
        i += span;
      });
    });
  }
  function labelAll() { $$('.table-wrapper table').forEach(labelTable); }
  function watchTables() {
    var busy = false;
    var mo = new MutationObserver(function () { if (busy) return; busy = true; requestAnimationFrame(function () { labelAll(); busy = false; }); });
    $$('.table-wrapper tbody').forEach(function (b) { mo.observe(b, { childList: true }); });
    labelAll();
  }

  /* edge swipe: right from the left edge opens, left closes */
  var sx = 0, sy = 0, tracking = false;
  document.addEventListener('touchstart', function (e) { if (!mq.matches) return; var t = e.touches[0]; sx = t.clientX; sy = t.clientY; tracking = sx < 22 || document.body.classList.contains('px-nav-open'); }, { passive: true });
  document.addEventListener('touchend', function (e) {
    if (!tracking) return; tracking = false; var t = e.changedTouches[0], dx = t.clientX - sx, dy = Math.abs(t.clientY - sy);
    if (dy > 60) return; if (dx > 70 && !document.body.classList.contains('px-nav-open')) setOpen(true); else if (dx < -70) setOpen(false);
  }, { passive: true });
  (mq.addEventListener ? mq.addEventListener.bind(mq, 'change') : mq.addListener.bind(mq))(function (e) { if (!e.matches) setOpen(false); });

  function boot() { build(); watchTables(); }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot); else boot();
})();
