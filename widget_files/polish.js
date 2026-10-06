/*
 * Sahasra chat widget — behaviour layer. Load AFTER the main script in index.html:
 *     <link rel="stylesheet" href="theme.css">   (in <head>)
 *     <script src="polish.js"></script>          (last thing in <body>)
 * Wraps the existing functions (addMessage, applyWidgetConfig, handleSend); nothing in them is replaced.
 */
(function () {
  'use strict';

  var PATHS = {
    spark: '<path d="M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9z"/><path d="M19 15l.7 1.8 1.8.7-1.8.7L19 20l-.7-1.8-1.8-.7 1.8-.7z"/>',
    send: '<path d="m5 12 7-7 7 7"/><path d="M12 19V5"/>',
    copy: '<rect width="14" height="14" x="8" y="8" rx="2" ry="2"/><path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/>',
    check: '<path d="M20 6 9 17l-5-5"/>',
    info: '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/>',
    down: '<path d="M12 5v14"/><path d="m19 12-7 7-7-7"/>'
  };
  function icon(n) { return '<svg viewBox="0 0 24 24" aria-hidden="true">' + PATHS[n] + '</svg>'; }
  function qs(s, r) { return (r || document).querySelector(s); }
  function esc(s) { return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;'); }

  /* ----------------------------------------------------------- theme param */
  var theme = new URLSearchParams(location.search).get('theme');
  if (theme === 'dark' || theme === 'light') document.documentElement.setAttribute('data-theme', theme);

  /* ------------------------------------------------------------- markdown */
  function inline(s) {
    return s.split(/(`[^`]+`)/).map(function (part, i) {
      if (i % 2) return '<code>' + part.slice(1, -1) + '</code>';
      return part
        .replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>')
        .replace(/(^|[\s(])(https?:\/\/[^\s<)]+)/g, '$1<a href="$2" target="_blank" rel="noopener noreferrer">$2</a>')
        .replace(/\*\*([^*\n]+)\*\*/g, '<b>$1</b>').replace(/__([^_\n]+)__/g, '<b>$1</b>')
        .replace(/(^|[^*\w])\*([^*\s][^*\n]*?)\*(?!\w)/g, '$1<i>$2</i>');
    }).join('');
  }
  var TABLE_SEP = /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/;
  function cells(line) { return line.trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map(function (c) { return c.trim(); }); }
  function renderMarkdown(src) {
    var lines = String(src == null ? '' : src).replace(/\r\n/g, '\n').split('\n'), out = [], i = 0, m;
    function blockStart(l) { return /^```/.test(l) || /^#{1,4}\s/.test(l) || /^\s*([-*•]|\d+[.)])\s+/.test(l) || /^\s*>/.test(l) || /^\s*(-{3,}|\*{3,})\s*$/.test(l) || (/^\s*\|.*\|\s*$/.test(l)); }
    while (i < lines.length) {
      var line = lines[i];
      if ((m = line.match(/^```[\w-]*\s*$/))) { var buf = []; i++; while (i < lines.length && !/^```\s*$/.test(lines[i])) buf.push(lines[i++]); i++; out.push('<pre><code>' + esc(buf.join('\n')) + '</code></pre>'); continue; }
      if (/^\s*$/.test(line)) { i++; continue; }
      if ((m = line.match(/^(#{1,4})\s+(.*)$/))) { out.push('<h' + m[1].length + '>' + inline(esc(m[2])) + '</h' + m[1].length + '>'); i++; continue; }
      if (/^\s*(-{3,}|\*{3,})\s*$/.test(line)) { out.push('<hr>'); i++; continue; }
      if (/^\s*\|.*\|\s*$/.test(line) && i + 1 < lines.length && TABLE_SEP.test(lines[i + 1])) {
        var head = cells(line), rows = []; i += 2;
        while (i < lines.length && /^\s*\|.*\|\s*$/.test(lines[i])) rows.push(cells(lines[i++]));
        out.push('<div class="tbl"><table><thead><tr>' + head.map(function (c) { return '<th>' + inline(esc(c)) + '</th>'; }).join('') + '</tr></thead><tbody>' +
          rows.map(function (r) { return '<tr>' + head.map(function (_, k) { return '<td>' + inline(esc(r[k] || '')) + '</td>'; }).join('') + '</tr>'; }).join('') + '</tbody></table></div>');
        continue;
      }
      if (/^\s*>/.test(line)) { var q = []; while (i < lines.length && /^\s*>/.test(lines[i])) q.push(lines[i++].replace(/^\s*>\s?/, '')); out.push('<blockquote>' + inline(esc(q.join('\n'))).replace(/\n/g, '<br>') + '</blockquote>'); continue; }
      if (/^\s*([-*•])\s+/.test(line)) { var ul = []; while (i < lines.length && /^\s*([-*•])\s+/.test(lines[i])) ul.push('<li>' + inline(esc(lines[i++].replace(/^\s*([-*•])\s+/, ''))) + '</li>'); out.push('<ul>' + ul.join('') + '</ul>'); continue; }
      if (/^\s*\d+[.)]\s+/.test(line)) { var ol = []; while (i < lines.length && /^\s*\d+[.)]\s+/.test(lines[i])) ol.push('<li>' + inline(esc(lines[i++].replace(/^\s*\d+[.)]\s+/, ''))) + '</li>'); out.push('<ol>' + ol.join('') + '</ol>'); continue; }
      var para = []; while (i < lines.length && !/^\s*$/.test(lines[i]) && (para.length === 0 || !blockStart(lines[i]))) para.push(lines[i++]);
      out.push('<p>' + inline(esc(para.join('\n'))).replace(/\n/g, '<br>') + '</p>');
    }
    return out.join('');
  }

  /* -------------------------------------------------------- message upgrade */
  function copyText(text, btn) {
    function done() { btn.innerHTML = icon('check'); btn.classList.add('ok'); setTimeout(function () { btn.innerHTML = icon('copy'); btn.classList.remove('ok'); }, 1500); }
    if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(text).then(done, fallback); else fallback();
    function fallback() { var t = document.createElement('textarea'); t.value = text; t.style.position = 'fixed'; t.style.opacity = '0'; document.body.appendChild(t); t.select(); try { document.execCommand('copy'); done(); } catch (e) {} t.remove(); }
  }
  function upgrade(div, text, type) {
    var time = qs('.time', div), stamp = time ? time.textContent : '';
    div.innerHTML = '<div class="md">' + (type === 'bot' ? renderMarkdown(text) : esc(text).replace(/\n/g, '<br>')) + '</div><div class="meta"><span class="msg-actions"></span><span class="time">' + stamp + '</span></div>';
    if (type === 'bot') {
      var b = document.createElement('button'); b.type = 'button'; b.setAttribute('aria-label', 'Copy reply'); b.title = 'Copy'; b.innerHTML = icon('copy');
      b.addEventListener('click', function () { copyText(text, b); }); qs('.msg-actions', div).appendChild(b);
    }
  }

  /* ----------------------------------------------------------- brand accent */
  function restyle() {
    var cfg = (typeof widgetConfig !== 'undefined' && widgetConfig) || {}, root = document.documentElement.style;
    var header = qs('.header'), chat = qs('.chat'), box = qs('.container');
    if (header) header.style.removeProperty('background');
    if (chat) chat.style.removeProperty('background-color');
    if (box) box.style.width = '100%';
    var legacy = ['#8b008b', '#1e293b'], p = /^#[0-9a-f]{6}$/i.test(cfg.primary_color || '') && legacy.indexOf(cfg.primary_color.toLowerCase()) < 0 ? cfg.primary_color : '';
    ['--w-accent', '--w-accent-2', '--w-accent-soft', '--w-accent-ink', '--w-ring', '--w-on-accent'].forEach(function (k) { root.removeProperty(k); });
    if (p) {
      var n = parseInt(p.slice(1), 16), lum = (0.299 * ((n >> 16) & 255) + 0.587 * ((n >> 8) & 255) + 0.114 * (n & 255)) / 255;
      root.setProperty('--w-accent', p); root.setProperty('--w-accent-2', 'color-mix(in srgb, ' + p + ' 82%, #000)');
      root.setProperty('--w-accent-soft', 'color-mix(in srgb, ' + p + ' 13%, transparent)'); root.setProperty('--w-accent-ink', 'color-mix(in srgb, ' + p + ' 70%, var(--w-ink))');
      root.setProperty('--w-ring', 'color-mix(in srgb, ' + p + ' 30%, transparent)'); root.setProperty('--w-on-accent', lum > 0.62 ? '#0b0b10' : '#ffffff');
    }
    var logo = qs('.logo');
    if (logo && cfg.icon_url && /^https?:\/\//i.test(cfg.icon_url) && logo.dataset.src !== cfg.icon_url) {
      logo.dataset.src = cfg.icon_url; var img = new Image(); img.alt = ''; img.onload = function () { logo.innerHTML = ''; logo.appendChild(img); }; img.src = cfg.icon_url;
    }
  }

  /* ------------------------------------------------------------ DOM chrome */
  function buildChrome() {
    var logo = qs('.logo'); if (logo && !logo.querySelector('svg') && !logo.dataset.src) logo.innerHTML = icon('spark');
    var chat = qs('#chat'); if (chat) { chat.setAttribute('role', 'log'); chat.setAttribute('aria-live', 'polite'); chat.setAttribute('aria-relevant', 'additions'); }

    var area = qs('.input-area'), input = qs('#msg'), send = area && qs('button[onclick="handleSend()"]', area);
    if (area && input && send && !qs('.composer', area)) {
      var wrap = document.createElement('div'); wrap.className = 'composer'; area.insertBefore(wrap, input); wrap.appendChild(input); wrap.appendChild(send);
      send.className = 'send'; send.type = 'button'; send.innerHTML = icon('send'); send.setAttribute('aria-label', 'Send message'); send.removeAttribute('style'); send.disabled = true;
      input.setAttribute('aria-label', 'Message'); input.setAttribute('autocomplete', 'off');
      input.addEventListener('input', function () { send.disabled = !input.value.trim(); });
      var hs = window.handleSend; window.handleSend = function () { var r = hs.apply(this, arguments); send.disabled = !input.value.trim(); return r; };
      if (!(window.matchMedia && matchMedia('(pointer: coarse)').matches)) { try { input.focus({ preventScroll: true }); } catch (e) {} }
    }

    var infoSpan = qs('[onclick*="disclaimerModal"]'), foot = infoSpan && infoSpan.parentElement;
    if (foot && !foot.classList.contains('foot')) { foot.removeAttribute('style'); foot.classList.add('foot'); infoSpan.removeAttribute('style'); infoSpan.className = 'info'; infoSpan.setAttribute('role', 'button'); infoSpan.setAttribute('aria-label', 'Disclaimer'); infoSpan.innerHTML = icon('info'); }

    var box = qs('.container');
    if (box && chat && !qs('#toBottom')) {
      var tb = document.createElement('button'); tb.id = 'toBottom'; tb.type = 'button'; tb.setAttribute('aria-label', 'Scroll to latest message'); tb.innerHTML = icon('down'); box.appendChild(tb);
      function far() { return chat.scrollHeight - chat.scrollTop - chat.clientHeight > 160; }
      function sync() { tb.classList.toggle('show', far()); }
      chat.addEventListener('scroll', sync, { passive: true }); new MutationObserver(function () { setTimeout(sync, 60); }).observe(chat, { childList: true });
      tb.addEventListener('click', function () { chat.scrollTo({ top: chat.scrollHeight, behavior: 'smooth' }); });
    }
  }

  /* ------------------------------------------------------------------ wrap */
  var addMessage0 = window.addMessage;
  window.addMessage = function (text, type) {
    var div = addMessage0.apply(this, arguments);
    if (div && div.classList && (type === 'bot' || type === 'user')) { try { upgrade(div, text, type); } catch (e) { console.warn('[widget polish]', e); } }
    return div;
  };
  var apply0 = window.applyWidgetConfig;
  window.applyWidgetConfig = function () { var r = apply0.apply(this, arguments); try { restyle(); } catch (e) {} return r; };

  buildChrome(); restyle();
  window.__widgetPolish = { renderMarkdown: renderMarkdown };
})();
