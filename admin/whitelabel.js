/*
 * White-label section for Admin → Chatbot Settings.
 * Self-contained: injects itself at the top of the Chatbot Settings page, so no
 * HTML has to be edited. Load it AFTER app.js:
 *     <script src="whitelabel.js"></script>
 * Uses only helpers app.js already defines: authFetch, API_BASE, pages, toast.
 */
(function () {
  'use strict';

  var PLATFORMS = [['html', 'HTML'], ['javascript', 'JavaScript'], ['java', 'Java'], ['python', 'Python'], ['dotnet', '.NET (C#)'],
                   ['php', 'PHP'], ['node', 'Node.js'], ['wordpress', 'WordPress'], ['react', 'React'], ['nextjs', 'Next.js'],
                   ['angular', 'Angular'], ['vue', 'Vue'], ['iframe', 'iframe'], ['builders', 'Wix / Shopify / Others'],
                   ['android', 'Android (Kotlin)'], ['flutter', 'Flutter'], ['ios', 'iOS (Swift)']];
  var MODES = [['b2c', 'B2C', 'Free public mode for patients / customers'],
               ['b2b', 'B2B', 'Paid mode for business companies'],
               ['admin', 'Admin', 'Activation code → live data, role based (no Smart Report PDF)']];

  var S = { label: 'normal', clients: [], clientId: '', client: null, cfg: null,
            url: '', embedMode: '', embed: null, platform: 'html', busy: false };

  function esc(v) {
    return String(v == null ? '' : v).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function say(msg) { if (typeof toast === 'function') toast(msg); else console.log('[whitelabel]', msg); }
  function api(path, opts) {
    return authFetch(API_BASE + path, opts).then(function (r) {
      return r.json().then(function (d) {
        if (!r.ok) throw new Error(d.detail || d.message || ('Request failed (' + r.status + ')'));
        if (d.status === 'error') throw new Error(d.message || 'Request failed');
        return d;
      });
    });
  }
  function jsonOpts(method, body) {
    return { method: method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) };
  }

  // ---------------------------------------------------------------- render
  function modeRows() {
    var c = S.cfg;
    return MODES.map(function (m) {
      return '<div class="setting"><div><strong>' + m[1] + ' mode</strong><small>' + m[2] + '</small></div>' +
        '<label class="switch"><input type="checkbox" data-wl-mode="' + m[0] + '"' +
        (c[m[0] + '_enabled'] ? ' checked' : '') + '><span></span></label></div>';
    }).join('');
  }



  function embedSection() {
    var langOpts = PLATFORMS.map(function (p) {
      return '<option value="' + p[0] + '"' + (S.platform === p[0] ? ' selected' : '') + '>' + esc(p[1]) + '</option>';
    }).join('');
    var modePick = '';
    if (S.label === 'white' && S.cfg) {
      var m = MODES.filter(function (x) { return S.cfg[x[0] + '_enabled']; }).map(function (x) {
        var cur = S.embedMode || S.cfg.default_mode;
        return '<option value="' + x[0] + '"' + (cur === x[0] ? ' selected' : '') + '>' + x[1] + '</option>';
      }).join('');
      modePick = '<div class="setting"><div><strong>Mode</strong></div><select id="wlEmbedMode" class="setting-input">' + m + '</select></div>';
    }
    var out = '';
    if (S.embed) {
      var snippets = S.embed.snippets || [];
      var cur2 = snippets.filter(function (x) { return x.id === S.platform; })[0] || snippets[0];
      var box = function (id, title, note, text, rows) {
        return '<div style="margin-top:10px;"><div style="display:flex;justify-content:space-between;align-items:center;">' +
          '<strong style="font-size:11px;">' + title + '</strong><button class="secondary-btn" data-wl-copy="' + id + '">Copy</button></div>' +
          (note ? '<div style="font-size:10px;color:#94a3b8;margin:2px 0 4px;">' + esc(note) + '</div>' : '') +
          '<textarea id="' + id + '" class="setting-input" rows="' + rows + '" readonly style="width:100%;font-family:monospace;font-size:11px;">' + esc(text) + '</textarea></div>';
      };
      out = box('wlOutUrl', 'Embed URL', '', S.embed.embed_url, 2) + (cur2 ? box('wlOutCode', 'Embed code', cur2.where, cur2.code, 10) : '');
    }
    return '<div class="setting"><div><strong>Input URL</strong></div>' +
      '<input id="wlUrl" class="setting-input" value="' + esc(S.url) + '" placeholder="https://www.example.com"></div>' +
      '<div class="setting"><div><strong>Language</strong></div><select id="wlPlatform" class="setting-input">' + langOpts + '</select></div>' +
      modePick +
      '<div style="margin-top:10px;"><button class="primary-btn" id="wlGenerate"' + (S.busy ? ' disabled' : '') + '>Generate Embed URL</button></div>' + out;
  }

  function render() {
    var root = document.getElementById('wlPanel');
    if (!root) return;
    root.innerHTML =
      '<h3>Chatbot Label &amp; Embed</h3>' +
      '<p style="font-size:10px;color:#94a3b8;margin-bottom:12px;">Choose which chatbot you are generating an embed for. ' +
      'Normal = the Athentech Sahasra chatbot. White label = a customised chatbot for one LIS/HIS client.</p>' +
      '<div class="setting"><div><strong>Label</strong></div><div>' +
      '<label style="margin-right:14px;"><input type="radio" name="wlLabel" value="normal"' + (S.label === 'normal' ? ' checked' : '') + '> Normal label</label>' +
      '<label><input type="radio" name="wlLabel" value="white"' + (S.label === 'white' ? ' checked' : '') + '> White label</label></div></div>' +
      (S.label === 'white' ? whiteSection() : '') +
      '<div style="border-top:1px solid #e2e8f0;margin:14px 0 8px;"></div>' + embedSection();
  }

  // ---------------------------------------------------------------- data
  function loadClient(id) {
    S.clientId = id; S.cfg = null; S.client = null; S.embed = null; S.embedMode = '';
    if (!id) return render();
    api('/admin/whitelabel/' + encodeURIComponent(id)).then(function (d) {
      S.cfg = d.config; S.client = d.client;
      if (d.config.configured) { S.url = d.config.site_url || S.url; }
      render();
    }).catch(function (e) { say(e.message); render(); });
  }

  function readCfgFromForm() {
    var modes = {};
    document.querySelectorAll('[data-wl-mode]').forEach(function (el) { modes[el.getAttribute('data-wl-mode') + '_enabled'] = el.checked; });
    var v = function (id) { var el = document.getElementById(id); return el ? el.value : ''; };
    var chk = function (id) { var el = document.getElementById(id); return !!(el && el.checked); };
    var num = function (id, d) { var n = Number(v(id)); return isFinite(n) ? n : d; };
    return Object.assign({
      enabled: chk('wlEnabled'),
      default_mode: v('wlDefaultMode'),
      brand_name: v('wlBrand'),
      brand_logo_url: v('wlLogo'),
      primary_color: v('wlColor'),
      welcome_message: v('wlWelcome'),
      b2c_knowledge: v('wlKnowledge'),
      b2b_notice: v('wlB2bNotice'),
      smart_report_enabled: chk('wlSmart'),
      site_url: v('wlUrl'),
      subtitle: v('wlSubtitle'),
      secondary_color: v('wlSecondary'),
      bg_color: v('wlBg'),
      footer_text: v('wlFooter'),
      disclaimer_text: v('wlDisclaimer'),
      width_px: num('wlWidth', 420),
      height_px: num('wlHeight', 700),
      max_history: num('wlMaxHistory', 50),
      session_timeout_min: num('wlSessionTimeout', 0),
      preview_toast_enabled: chk('wlPreviewToast'),
      escalate_phone: v('wlEscalatePhone'),
      escalate_message: v('wlEscalateMsg'),
      idle_nudge_enabled: chk('wlIdleEnabled'),
      idle_nudge_minutes: num('wlIdleMinutes', 3),
      idle_nudge_message: v('wlIdleMsg'),
    }, modes);
  }

  // Keep what the admin has typed when the panel re-renders (language tick, mode switch, ...).
  function syncFromForm() {
    var u = document.getElementById('wlUrl');
    if (u) S.url = u.value;
    if (S.label === 'white' && S.cfg && document.getElementById('wlBrand')) {
      var f = readCfgFromForm(); delete f.site_url;
      Object.assign(S.cfg, f);
    }
  }

  function saveWhite() {
    if (!S.clientId) return say('Choose a client first');
    api('/admin/whitelabel/' + encodeURIComponent(S.clientId), jsonOpts('PUT', readCfgFromForm()))
      .then(function (d) { S.cfg = d.config; if (d.config.site_url) S.url = d.config.site_url; say('White-label settings saved'); render(); })
      .catch(function (e) { say(e.message); });
  }

  function generate() {
    syncFromForm();
    S.url = (document.getElementById('wlUrl') || {}).value || '';
    var body = { label: S.label, url: S.url };
    if (S.label === 'white') {
      if (!S.clientId) return say('Choose a client first');
      body.institution_id = Number(S.clientId);
      body.mode = (document.getElementById('wlEmbedMode') || {}).value || (S.cfg && S.cfg.default_mode);
      S.embedMode = body.mode;
    }
    S.busy = true; render();
    api('/admin/embed', jsonOpts('POST', body))
      .then(function (d) { S.embed = d; })
      .catch(function (e) { S.embed = null; say(e.message); })
      .then(function () { S.busy = false; render(); });
  }

  // ---------------------------------------------------------------- events (delegated, survive re-render)
  function onChange(e) {
    var t = e.target;
    syncFromForm();
    if (t.name === 'wlLabel') { S.label = t.value; S.embed = null; render(); if (S.label === 'white' && !S.clients.length) loadClients(); return; }
    if (t.id === 'wlClient') return loadClient(t.value);
    if (t.id === 'wlPlatform') { S.platform = t.value; return render(); }
    if (t.id === 'wlEmbedMode') { S.embedMode = t.value; return; }
    if (t.hasAttribute('data-wl-mode') && S.cfg) {   // keep the default-mode list in sync
      var key = t.getAttribute('data-wl-mode') + '_enabled';
      S.cfg = Object.assign({}, S.cfg, readCfgFromForm());
      S.cfg[key] = t.checked;
      if (!S.cfg[S.cfg.default_mode + '_enabled']) {
        var first = MODES.filter(function (m) { return S.cfg[m[0] + '_enabled']; })[0];
        S.cfg.default_mode = first ? first[0] : 'b2c';
      }
      render();
    }
  }
  function onClick(e) {
    var t = e.target;
    if (t.id === 'wlSave') return saveWhite();
    if (t.id === 'wlGenerate') return generate();
    var copy = t.getAttribute && t.getAttribute('data-wl-copy');
    if (copy) {
      var el = document.getElementById(copy);
      if (el) { el.select(); (navigator.clipboard ? navigator.clipboard.writeText(el.value) : Promise.reject()).then(
        function () { say('Copied'); }, function () { document.execCommand('copy'); say('Copied'); }); }
    }
  }

  function loadClients() {
    api('/admin/whitelabel/clients').then(function (d) { S.clients = d.clients || []; render(); })
      .catch(function (e) { say(e.message); });
  }

  // ---------------------------------------------------------------- mount
  function host() {
    return (typeof pages !== 'undefined' && pages && pages.chatbotSettings) ||
           document.getElementById('chatbotSettingsPage');
  }
  function mount() {
    var h = host();
    if (!h || document.getElementById('wlPanel')) return;
    var panel = document.createElement('div');
    panel.id = 'wlPanel';
    panel.className = 'settings-section';
    h.insertBefore(panel, h.firstChild);
    panel.addEventListener('change', onChange);
    panel.addEventListener('click', onClick);
    render();
    if (S.label === 'white') loadClients();
  }

  function install() {
    if (typeof window.navigate !== 'function') { console.warn('[whitelabel] navigate() not found — panel not installed'); return; }
    var original = window.navigate;
    window.navigate = function (page) {
      var result = original.apply(this, arguments);
      if (page === 'chatbotSettings') { setTimeout(mount, 0); setTimeout(mount, 700); }  // re-mount if the page re-renders
      return result;
    };
    if (location.hash === '#chatbotSettings') setTimeout(mount, 300);
  }

  install();
  window.__wlMount = mount;   // handy for debugging from the browser console
})();