/* Sahasra widget - live progress while the AI works. Additive and self-contained:
   POST .../ask is sent to .../ask/stream (server-sent events). The typing bubble shows what is happening
   ("Querying your database..."); the final JSON is handed back to the widget exactly as /ask would.
   Any problem (old server, proxy that buffers streams, network blip before start) -> silently uses plain /ask.
   Off switch: ?stream=off. Must load BEFORE polish.js so polish.js still sees the /ask reply (follow-up chips). */
(function () {
  'use strict';
  if (/[?&]stream=off/.test(location.search) || !window.ReadableStream || !window.TextDecoder) return;
  var fetch0 = window.fetch.bind(window), broken = false;

  function label(text) {
    var el = document.querySelector('.typing-indicator:last-of-type') || document.querySelector('.typing-indicator');
    if (!el) return;
    var s = el.querySelector('.sx-status');
    if (!s) {
      s = document.createElement('small'); s.className = 'sx-status';
      s.style.cssText = 'display:block;margin-top:6px;font-size:12px;opacity:.75;transition:opacity .2s';
      el.appendChild(s);
    }
    s.textContent = text;
  }

  window.fetch = function (input, init) {
    var url = typeof input === 'string' ? input : (input && input.url) || '';
    var path; try { path = new URL(url, location.href).pathname; } catch (e) { return fetch0(input, init); }
    if (broken || !/\/ask$/.test(path) || !init || String(init.method || 'GET').toUpperCase() !== 'POST')
      return fetch0(input, init);
    var streamUrl = url.replace(/\/ask(\?.*)?$/, '/ask/stream$1');
    var slow = setTimeout(function () { label('Still working — bigger questions take a little longer…'); }, 9000);

    return fetch0(streamUrl, init).then(function (res) {
      var ct = (res.headers.get('content-type') || '');
      if (!res.ok || ct.indexOf('text/event-stream') < 0 || !res.body) { broken = !res.ok && res.status === 404; throw new Error('nostream'); }
      var reader = res.body.getReader(), dec = new TextDecoder(), buf = '', done = null;
      return (function pump() {
        return reader.read().then(function (r) {
          if (r.done) return done;
          buf += dec.decode(r.value, { stream: true });
          var parts = buf.split('\n\n'); buf = parts.pop();
          parts.forEach(function (blk) {
            var ev = /^event: (.*)$/m.exec(blk), dt = /^data: (.*)$/m.exec(blk);
            if (!ev || !dt) return;
            var data; try { data = JSON.parse(dt[1]); } catch (e) { return; }
            if (ev[1] === 'status') label(data);
            else if (ev[1] === 'done') done = data;
          });
          return done ? done : pump();
        });
      })().then(function (d) {
        if (!d) throw new Error('nostream');
        return new Response(JSON.stringify(d), { status: 200, headers: { 'Content-Type': 'application/json' } });
      });
    }).catch(function (e) {
      return fetch0(input, init);          // plain /ask
    }).then(function (r) { clearTimeout(slow); return r; }, function (e) { clearTimeout(slow); throw e; });
  };
})();
