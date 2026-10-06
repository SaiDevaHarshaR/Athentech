/**
 * Sahasra AI Assistant — widget loader.
 * Floating chat bubble that opens the real widget in an iframe.
 *
 * Normal label (no config)  -> exactly the Athentech-branded bubble, as before.
 * White label               -> a client-branded bubble. Configured by what the admin
 *                              panel's "Generate Embed URL" produces:
 *
 *   <script>window.SahasraChat = {"label":"white","client":"KLIS","mode":"b2c",
 *                                 "lang":"en","langs":["en","hi"],"site":"https://www.klis.in"};</script>
 *   <script src="https://YOUR-HOST/widget-loader.js" defer></script>
 *
 * (the same keys also work as data-label / data-client / ... on the <script> tag).
 *
 * The widget page is found next to this file (…/widget_files/index.html), so nothing
 * is hardcoded and nothing needs editing per server. Override with "widget" if the
 * widget is hosted elsewhere.
 */
(function () {
  if (document.getElementById("sahasra-widget-bubble")) return; // already loaded on this page

  var scriptEl = document.currentScript || document.querySelector('script[src*="widget-loader"]');

  // ---- read + validate the embed config -------------------------------------------------
  var cfg = {};
  try { cfg = Object.assign({}, window.SahasraChat || {}); } catch (e) {}
  if (scriptEl && scriptEl.dataset) {
    ["label", "client", "mode", "lang", "langs", "site", "widget"].forEach(function (k) {
      if (scriptEl.dataset[k] && cfg[k] == null) cfg[k] = scriptEl.dataset[k];
    });
  }
  var hasConfig = Object.keys(cfg).length > 0;
  var label = String(cfg.label || "normal").toLowerCase() === "white" ? "white" : "normal";
  var isWhite = label === "white";

  function cleanOrigin(v) {
    try { var u = new URL(String(v)); return /^https?:$/.test(u.protocol) ? u.origin : ""; } catch (e) { return ""; }
  }
  var client = String(cfg.client || "");
  var mode = String(cfg.mode || "").toLowerCase();
  var lang = String(cfg.lang || "").toLowerCase();
  var langs = (Array.isArray(cfg.langs) ? cfg.langs : String(cfg.langs || "").split(","))
    .map(function (x) { return String(x).trim().toLowerCase(); })
    .filter(function (x) { return /^[a-z]{2,3}$/.test(x); });

  if (isWhite && !/^[A-Za-z0-9_-]{1,50}$/.test(client)) {
    console.error("[Sahasra] White-label embed needs a valid 'client'. Chat not loaded.");
    return; // never fall back to the Athentech-branded bot on a client's site
  }

  // ---- where the widget page lives ------------------------------------------------------
  var WIDGET_URL = "";
  if (cfg.widget && /^https?:\/\//i.test(String(cfg.widget))) {
    WIDGET_URL = String(cfg.widget);
  } else if (scriptEl && scriptEl.src) {
    WIDGET_URL = new URL("widget_files/index.html", scriptEl.src).href;
  } else {
    console.error("[Sahasra] Cannot locate the widget page (no script src). Chat not loaded.");
    return;
  }

  var qs = new URLSearchParams();
  if (hasConfig) qs.set("label", label);
  if (isWhite) {
    qs.set("client", client);
    if (/^(b2c|b2b|admin)$/.test(mode)) qs.set("mode", mode);
  }
  if (/^[a-z]{2,3}$/.test(lang)) qs.set("lang", lang);
  if (langs.length > 1) qs.set("langs", langs.join(","));
  if (cleanOrigin(cfg.site)) qs.set("site", cleanOrigin(cfg.site));          // where the admin said it will be used
  if (isWhite) qs.set("embedder", location.origin);                          // where it actually is — widget compares the two
  var query = qs.toString();
  if (query) WIDGET_URL += (WIDGET_URL.indexOf("?") >= 0 ? "&" : "?") + query;

  // neutral until the client's own brand arrives from the widget (no Athentech purple flash on a client site)
  var BUBBLE_BG = isWhite ? "#334155" : "linear-gradient(140deg, #8b7dff, #5748e8)";
  var SVG = 'width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"';
  var ICON_CHAT = '<svg ' + SVG + '><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/><path d="M8 9h8"/><path d="M8 13h5"/></svg>';
  var ICON_CLOSE = '<svg ' + SVG + '><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>';
  var BOT_TITLE = isWhite ? "Chat assistant" : "Sahasra AI Assistant";

  var bubble = document.createElement("div");
  bubble.id = "sahasra-widget-bubble";
  bubble.setAttribute("role", "button");
  bubble.setAttribute("aria-label", "Open chat");
  bubble.innerHTML = ICON_CHAT;
  bubble.style.cssText = [
    "position: fixed",
    "bottom: 20px",
    "right: 20px",
    "width: 64px",
    "height: 64px",
    "border-radius: 50%",
    "background: " + BUBBLE_BG,
    "color: white",
    "display: flex",
    "align-items: center",
    "justify-content: center",
    "cursor: pointer",
    "box-shadow: 0 8px 24px rgba(87,72,232,0.35), 0 2px 6px rgba(0,0,0,0.18), inset 0 1px 0 rgba(255,255,255,0.28)",
    "z-index: 999998",
    "transition: transform 0.2s cubic-bezier(0.34, 1.56, 0.64, 1), box-shadow 0.2s ease",
    "animation: sahasra-bubble-pop 0.4s cubic-bezier(0.34, 1.56, 0.64, 1)",
  ].join(";");
  bubble.onmouseenter = function () {
    bubble.style.transform = "scale(1.1)";
    bubble.style.boxShadow = "0 12px 30px rgba(87,72,232,0.45), 0 2px 6px rgba(0,0,0,0.2), inset 0 1px 0 rgba(255,255,255,0.28)";
  };
  bubble.onmouseleave = function () {
    bubble.style.transform = "scale(1)";
    bubble.style.boxShadow = "0 8px 24px rgba(87,72,232,0.35), 0 2px 6px rgba(0,0,0,0.18), inset 0 1px 0 rgba(255,255,255,0.28)";
  };

  var style = document.createElement("style");
  style.textContent =
    "@keyframes sahasra-bubble-pop { 0% { transform: scale(0); opacity: 0; } 60% { transform: scale(1.15); opacity: 1; } 100% { transform: scale(1); } }" +
    "@keyframes sahasra-frame-open { 0% { transform: translateY(20px) scale(0.95); opacity: 0; } 100% { transform: translateY(0) scale(1); opacity: 1; } }";
  style.textContent +=
    "#sahasra-widget-bar{display:none}" +
    "@media (max-width:520px){" +
    "#sahasra-widget-frame-wrap{inset:0 !important;width:100vw !important;height:100vh !important;height:100dvh !important;max-width:none !important;max-height:none !important;border-radius:0 !important;display:none}" +
    "#sahasra-widget-frame-wrap.sahasra-open{display:flex !important;flex-direction:column}" +
    "#sahasra-widget-frame-wrap iframe{flex:1;min-height:0}" +
    "#sahasra-widget-bar{display:flex;align-items:center;justify-content:space-between;height:44px;padding:0 6px 0 16px;background:#0b0b10;color:#fff;font:600 14px system-ui,-apple-system,'Segoe UI',sans-serif}" +
    "#sahasra-widget-bar button{width:44px;height:44px;border:0;background:transparent;color:#fff;display:grid;place-items:center;cursor:pointer}" +
    "#sahasra-widget-badge,#sahasra-widget-bubble{z-index:999998}" +
    "}";
  document.head.appendChild(style);

  var frameWrap = document.createElement("div");
  frameWrap.id = "sahasra-widget-frame-wrap";
  frameWrap.style.cssText = [
    "position: fixed",
    "bottom: 96px",
    "right: 20px",
    "width: 480px",
    "height: 85vh",
    "max-width: calc(100vw - 40px)",
    "max-height: 820px",
    "border-radius: 20px",
    "overflow: hidden",
    "box-shadow: 0 28px 70px rgba(10,10,20,0.32), 0 0 0 1px rgba(10,10,20,0.07)",
    "background: #fff",
    "display: none",
    "z-index: 999999",
    "animation: sahasra-frame-open 0.25s cubic-bezier(0.34, 1.56, 0.64, 1)",
  ].join(";");

  var iframe = document.createElement("iframe");
  iframe.src = WIDGET_URL;
  iframe.title = BOT_TITLE;
  iframe.style.cssText = "width: 100%; height: 100%; border: none;";
  var bar = document.createElement("div");
  bar.id = "sahasra-widget-bar";
  bar.innerHTML = '<span id="sahasra-bar-title"></span><button type="button" aria-label="Close chat"><svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg></button>';
  frameWrap.appendChild(bar);
  frameWrap.appendChild(iframe);

  var badge = document.createElement("div");
  badge.id = "sahasra-widget-badge";
  badge.style.cssText = [
    "position: absolute",
    "top: -4px",
    "right: -4px",
    "background: #ef4444",
    "color: white",
    "font-size: 11px",
    "font-weight: 700",
    "min-width: 20px",
    "height: 20px",
    "border-radius: 10px",
    "display: none",
    "align-items: center",
    "justify-content: center",
    "padding: 0 5px",
    "box-shadow: 0 0 0 2px white",
    "animation: sahasra-bubble-pop 0.3s cubic-bezier(0.34, 1.56, 0.64, 1)",
  ].join(";");
  badge.textContent = "1";
  bubble.style.position = "fixed"; // ensure bubble is the positioning context for the badge
  var bubbleWrap = document.createElement("div");
  bubbleWrap.style.cssText = "position: fixed; bottom: 20px; right: 20px; z-index: 999998;";
  bubble.style.position = "static";
  bubble.style.bottom = "auto";
  bubble.style.right = "auto";
  badge.style.position = "absolute";
  bubbleWrap.appendChild(bubble);
  bubbleWrap.appendChild(badge);

  var preview = document.createElement("div");
  preview.id = "sahasra-widget-preview";
  preview.style.cssText = [
    "position: fixed",
    "bottom: 96px",
    "right: 20px",
    "max-width: 280px",
    "background: white",
    "border-radius: 14px",
    "border-bottom-right-radius: 4px",
    "padding: 12px 14px",
    "box-shadow: 0 6px 24px rgba(0,0,0,0.2)",
    "display: none",
    "cursor: pointer",
    "z-index: 999998",
    "font-family: 'Segoe UI', system-ui, sans-serif",
    "animation: sahasra-frame-open 0.3s cubic-bezier(0.34, 1.56, 0.64, 1)",
  ].join(";");
  preview.innerHTML =
    '<div style="display:flex; gap:8px; align-items:flex-start;">' +
    '<div style="width:24px; height:24px; border-radius:50%; background:' + BUBBLE_BG + '; flex-shrink:0; display:flex; align-items:center; justify-content:center; font-size:12px; color:white; font-weight:700;">AI</div>' +
    '<div style="flex:1; min-width:0;">' +
    '<div id="sahasra-preview-title" style="font-size:11px; font-weight:700; color:#64748b; margin-bottom:2px;"></div>' +
    '<div id="sahasra-preview-text" style="font-size:13px; color:#1e293b; line-height:1.4;"></div>' +
    '</div>' +
    '<div style="color:#94a3b8; font-size:14px; flex-shrink:0;" onclick="event.stopPropagation(); document.getElementById(\'sahasra-widget-preview\').style.display=\'none\';">✕</div>' +
    '</div>';
  preview.addEventListener("click", function () {
    preview.style.display = "none";
    isOpen = true;
    frameWrap.style.display = "block";
    frameWrap.classList.add("sahasra-open");
    bubble.innerHTML = ICON_CLOSE;
  });

  // Listens for the widget (inside the iframe) posting a message whenever
  // a new bot reply arrives — only shows the preview while the widget is
  // closed, since an open widget means the person is already looking at it.
  var previewTitle = preview.querySelector("#sahasra-preview-title");
  previewTitle.textContent = BOT_TITLE;

  function applyBrand(b) {
    var name = typeof b.name === "string" ? b.name.trim().slice(0, 100) : "";
    if (name) { var bt = bar.querySelector("#sahasra-bar-title"); if (bt) bt.textContent = name; previewTitle.textContent = name; iframe.title = name; bubble.setAttribute("aria-label", "Open chat with " + name); }
    if (typeof b.primary_color === "string" && /^#[0-9a-fA-F]{6}$/.test(b.primary_color)) {
      bubble.style.background = b.primary_color;
      var av = preview.querySelector("div div"); if (av) av.style.background = b.primary_color;
    }
  }

  // Only messages that really come from our own iframe are trusted.
  window.addEventListener("message", function (event) {
    if (event.source !== iframe.contentWindow || !event.data) return;
    if (event.data.type === "sahasra-brand" && isWhite) { applyBrand(event.data); return; }
    if (event.data.type === "sahasra-new-message" && !isOpen) {
      badge.style.display = "flex";
      var textEl = document.getElementById("sahasra-preview-text");
      if (textEl) {
        textEl.textContent = event.data.preview || "New message";
      }
      preview.style.display = "block";
    }
  });

  var isOpen = false;
  bubble.addEventListener("click", function () {
    isOpen = !isOpen;
    frameWrap.style.display = isOpen ? "block" : "none";
    frameWrap.classList.toggle("sahasra-open", isOpen);
    bubble.innerHTML = isOpen ? ICON_CLOSE : ICON_CHAT;
    if (isOpen) {
      badge.style.display = "none";
      preview.style.display = "none";
    }
  });

  bar.querySelector("#sahasra-bar-title").textContent = BOT_TITLE;
  bar.querySelector("button").addEventListener("click", function () { bubble.click(); });

  document.body.appendChild(bubbleWrap);
  document.body.appendChild(preview);
  document.body.appendChild(frameWrap);
})();