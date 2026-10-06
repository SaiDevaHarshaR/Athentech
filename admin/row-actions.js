/*
 * Clear, colour-coded action buttons for the Institute Registry, License Management and Roles tables.
 * Self-contained: no edits to app.js. Load it after app.js:   <script src="row-actions.js"></script>
 * It recognises each button by the function its onclick calls and swaps the tiny text glyph for a
 * proper icon, a colour, and a tooltip. Re-runs automatically whenever a table is re-rendered.
 */
(function () {
  'use strict';

  var ICONS = {
    edit:   '<path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z"/><path d="m15 5 4 4"/>',
    key:    '<circle cx="7.5" cy="15.5" r="5.5"/><path d="m21 2-9.6 9.6"/><path d="m15.5 7.5 3 3L22 7l-3-3"/>',
    power:  '<path d="M12 2v10"/><path d="M18.4 6.6a9 9 0 1 1-12.77.04"/>',
    gauge:  '<path d="m12 14 4-4"/><path d="M3.34 19a10 10 0 1 1 17.32 0"/>',
    trash:  '<path d="M3 6h18"/><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/><path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/><path d="M10 11v6"/><path d="M14 11v6"/>',
    copy:   '<rect width="14" height="14" x="8" y="8" rx="2" ry="2"/><path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/>',
    pause:  '<rect x="14" y="4" width="4" height="16" rx="1"/><rect x="6" y="4" width="4" height="16" rx="1"/>',
    ban:    '<circle cx="12" cy="12" r="10"/><path d="m4.9 4.9 14.2 14.2"/>',
    play:   '<polygon points="7 3 20 12 7 21 7 3"/>',
    qr:     '<rect width="5" height="5" x="3" y="3" rx="1"/><rect width="5" height="5" x="16" y="3" rx="1"/><rect width="5" height="5" x="3" y="16" rx="1"/><path d="M21 16h-3a2 2 0 0 0-2 2v3"/><path d="M21 21v.01"/><path d="M12 7v3a2 2 0 0 1-2 2H7"/><path d="M3 12h.01"/><path d="M12 3h.01"/><path d="M12 16v.01"/><path d="M16 12h1"/><path d="M21 12v.01"/><path d="M12 21v-1"/>',
    dots:   '<circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/><circle cx="5" cy="12" r="1"/>'
  };

  // kind -> [icon, colour group, tooltip]
  var KINDS = {
    editInstitution:          ['edit',  'blue',   'Edit institution'],
    viewInstitutionLicenses:  ['key',   'indigo', 'View licenses'],
    toggleInstitution:        ['power', 'green',  'Activate / deactivate'],
    manageLimit:              ['gauge', 'orange', 'Request limit'],
    deleteInstitution:        ['trash', 'red',    'Delete institution'],
    copyLicense:              ['copy',  'slate',  'Copy activation code'],
    editLicense:              ['edit',  'blue',   'Edit license'],
    generateTotpQr:           ['qr',    'teal',   'Show QR / setup code'],
    deleteLicense:            ['trash', 'red',    'Delete license'],
    openRoleModal:            ['edit',  'blue',   'Edit role'],
    deleteRole:               ['trash', 'red',    'Delete role']
  };
  var LICENSE_ACTIONS = {
    suspend:    ['pause', 'amber', 'Suspend license'],
    revoke:     ['ban',   'red',   'Revoke license'],
    resume:     ['play',  'green', 'Reactivate license'],
    activate:   ['play',  'green', 'Reactivate license'],
    reactivate: ['play',  'green', 'Reactivate license'],
    unsuspend:  ['play',  'green', 'Reactivate license']
  };

  var COLORS = { blue: ['#2563eb', '#eff6ff'], indigo: ['#5b4fe0', '#f0eeff'], green: ['#16a34a', '#ecfdf3'], orange: ['#ea580c', '#fff4ec'],
                 red: ['#dc2626', '#fef2f2'], slate: ['#475569', '#f1f5f9'], amber: ['#d97706', '#fffbeb'], teal: ['#0d9488', '#effdfa'] };

  var css = '.row-actions{gap:8px!important;align-items:center}' +
    '.row-action.ra{width:36px;height:36px;padding:0!important;border-radius:11px;display:inline-flex;align-items:center;justify-content:center;' +
    'border:1px solid transparent;background:var(--ra-bg);color:var(--ra-fg);cursor:pointer;flex:none;' +
    'transition:transform .12s ease,box-shadow .12s ease,background .12s ease,color .12s ease}' +
    '.row-action.ra svg{width:19px;height:19px;stroke:currentColor;fill:none;stroke-width:2;stroke-linecap:round;stroke-linejoin:round;pointer-events:none}' +
    '.row-action.ra:hover{background:var(--ra-fg);color:#fff;transform:translateY(-2px);box-shadow:0 7px 14px rgba(17,24,39,.2)}' +
    '.row-action.ra:active{transform:translateY(0);box-shadow:none}' +
    '.row-action.ra:focus-visible{outline:2px solid var(--ra-fg);outline-offset:2px}' +
    Object.keys(COLORS).map(function (k) { return '.row-action.ra[data-c="' + k + '"]{--ra-fg:' + COLORS[k][0] + ';--ra-bg:' + COLORS[k][1] + '}'; }).join('') +
    '#raTip{position:fixed;z-index:99999;background:#111827;color:#fff;font:600 11px "DM Sans",system-ui,sans-serif;padding:6px 10px;border-radius:8px;' +
    'pointer-events:none;white-space:nowrap;opacity:0;transform:translateY(3px);transition:opacity .12s,transform .12s;box-shadow:0 6px 18px rgba(0,0,0,.25)}' +
    '#raTip.show{opacity:1;transform:none}';
  var style = document.createElement('style'); style.id = 'raStyle'; style.textContent = css; document.head.appendChild(style);

  function classify(btn) {
    var oc = (btn.getAttribute('onclick') || '').replace(/\s+/g, ' ');
    var m = oc.match(/\b(editInstitution|viewInstitutionLicenses|toggleInstitution|manageLimit|deleteInstitution|copyLicense|editLicense|generateTotpQr|deleteLicense|openRoleModal|deleteRole)\s*\(/);
    if (m) return KINDS[m[1]];
    var la = oc.match(/\blicenseAction\s*\([^,]*,\s*['"]([A-Za-z]+)['"]/);
    if (la) return LICENSE_ACTIONS[la[1].toLowerCase()] || ['dots', 'slate', la[1]];
    return null;
  }

  function enhance(root) {
    (root || document).querySelectorAll('.row-action:not([data-ra])').forEach(function (btn) {
      var k = classify(btn);
      if (!k) return;                                  // not one of ours: leave it exactly as it is
      btn.setAttribute('data-ra', '1');
      btn.classList.add('ra');
      btn.setAttribute('data-c', k[1]);
      btn.setAttribute('aria-label', k[2]);
      btn.setAttribute('data-tip', k[2]);
      btn.removeAttribute('title');                    // our tooltip replaces the slow native one
      btn.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true">' + ICONS[k[0]] + '</svg>';
    });
  }

  var tip = document.createElement('div'); tip.id = 'raTip'; document.body.appendChild(tip);
  document.addEventListener('mouseover', function (e) {
    var b = e.target.closest && e.target.closest('.row-action.ra');
    if (!b) return;
    tip.textContent = b.getAttribute('data-tip');
    var r = b.getBoundingClientRect(), w = tip.offsetWidth || 90;
    var left = Math.min(Math.max(8, r.left + r.width / 2 - w / 2), window.innerWidth - w - 8);
    tip.style.left = left + 'px';
    tip.style.top = (r.top > 44 ? r.top - 36 : r.bottom + 8) + 'px';
    tip.classList.add('show');
  });
  document.addEventListener('mouseout', function (e) { if (e.target.closest && e.target.closest('.row-action.ra')) tip.classList.remove('show'); });
  window.addEventListener('scroll', function () { tip.classList.remove('show'); }, true);

  var queued = false;
  new MutationObserver(function () {
    if (queued) return; queued = true;
    requestAnimationFrame(function () { queued = false; enhance(); });
  }).observe(document.body, { childList: true, subtree: true });
  enhance();
  window.__raEnhance = enhance;
})();