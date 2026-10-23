/**
 * AthenTech chat bubble — opens only on click
 * <script src="https://api.athentech.in/widget/athentech/loader.js" defer></script>
 */
(function () {
  if (document.getElementById("athentech-chat-bubble")) return;

  var WIDGET = "https://api.athentech.in/widget/athentech/index.html";
  try {
    var cfg = Object.assign({}, window.AthenTechChat || {});
    if (cfg.widget && /^https?:\/\//i.test(cfg.widget) && /\/widget\//i.test(cfg.widget)) {
      WIDGET = String(cfg.widget);
    }
  } catch (e) {}

  var style = document.createElement("style");
  style.textContent =
    "@keyframes at-bubble-in{from{opacity:0;transform:scale(.85) translateY(12px)}to{opacity:1;transform:scale(1) translateY(0)}}" +
    "@keyframes at-panel-in{from{opacity:0;transform:translateY(18px) scale(.97)}to{opacity:1;transform:translateY(0) scale(1)}}" +
    "@keyframes at-badge-pop{from{transform:scale(0)}to{transform:scale(1)}}" +
    "#athentech-chat-bubble{animation:at-bubble-in .4s ease-out}" +
    "#athentech-chat-panel.at-open{display:flex !important;animation:at-panel-in .28s ease-out}" +
    "#athentech-chat-badge{animation:at-badge-pop .25s ease-out}";
  document.head.appendChild(style);

  var ORANGE = "linear-gradient(135deg, #f97316, #ea580c)";
  var open = false;
  var unread = 1; // greeting waiting until first open
  var iframeLoaded = false;

  /* —— floating bubble —— */
  var bubble = document.createElement("button");
  bubble.id = "athentech-chat-bubble";
  bubble.type = "button";
  bubble.setAttribute("aria-label", "Open AthenTech Assistant");
  bubble.style.cssText =
    "position:fixed;bottom:22px;right:22px;width:60px;height:60px;border-radius:50%;border:none;" +
    "background:" + ORANGE + ";color:#fff;display:flex;align-items:center;justify-content:center;" +
    "cursor:pointer;box-shadow:0 10px 28px rgba(249,115,22,.42);z-index:2147483000;padding:0;";

  var iconChat =
    '<svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/><path d="M8 9h8"/><path d="M8 13h5"/></svg>';
  var iconClose =
    '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.4" stroke-linecap="round"><path d="M18 6 6 18"/><path d="m6 6 12 12"/></svg>';
  bubble.innerHTML = iconChat;

  var badge = document.createElement("span");
  badge.id = "athentech-chat-badge";
  badge.style.cssText =
    "position:absolute;top:-4px;right:-4px;min-width:20px;height:20px;padding:0 6px;border-radius:999px;" +
    "background:#ef4444;color:#fff;font:700 11px/20px system-ui,Segoe UI,sans-serif;text-align:center;" +
    "box-shadow:0 2px 8px rgba(239,68,68,.45);display:none;pointer-events:none;";
  bubble.style.position = "fixed";
  bubble.appendChild(badge);

  function renderBadge() {
    if (!open && unread > 0) {
      badge.textContent = unread > 9 ? "9+" : String(unread);
      badge.style.display = "block";
    } else {
      badge.style.display = "none";
    }
  }

  /* —— panel + chrome (close / minimize) —— */
  var panel = document.createElement("div");
  panel.id = "athentech-chat-panel";
  panel.style.cssText =
    "position:fixed;bottom:96px;right:22px;width:420px;height:640px;max-width:calc(100vw - 20px);" +
    "max-height:calc(100vh - 110px);border-radius:18px;overflow:hidden;box-shadow:0 20px 50px rgba(15,23,42,.22);" +
    "border:1px solid #e2e8f0;background:#fff;z-index:2147483000;display:none;flex-direction:column;";

  var chrome = document.createElement("div");
  chrome.style.cssText =
    "flex:0 0 auto;display:flex;align-items:center;justify-content:flex-end;gap:6px;" +
    "padding:6px 8px;background:linear-gradient(180deg,#fff7ed,#fff);border-bottom:1px solid #fed7aa;";

  function mkBtn(label, title) {
    var b = document.createElement("button");
    b.type = "button";
    b.title = title;
    b.setAttribute("aria-label", title);
    b.textContent = label;
    b.style.cssText =
      "width:28px;height:28px;border:none;border-radius:8px;background:#fff;color:#9a3412;" +
      "font:700 14px/1 system-ui,sans-serif;cursor:pointer;box-shadow:0 1px 3px rgba(15,23,42,.08);";
    b.onmouseenter = function () { b.style.background = "#ffedd5"; };
    b.onmouseleave = function () { b.style.background = "#fff"; };
    return b;
  }

  var btnMin = mkBtn("–", "Minimize");
  var btnClose = mkBtn("×", "Close");
  chrome.appendChild(btnMin);
  chrome.appendChild(btnClose);

  var iframe = document.createElement("iframe");
  iframe.title = "AthenTech Assistant";
  iframe.src = "about:blank";
  iframe.setAttribute("allow", "clipboard-write");
  iframe.style.cssText = "flex:1 1 auto;width:100%;height:100%;border:0;display:block;background:#fff;min-height:0;";

  panel.appendChild(chrome);
  panel.appendChild(iframe);

  function setOpen(v) {
    open = !!v;
    if (open) {
      panel.classList.add("at-open");
      panel.style.display = "flex";
      if (!iframeLoaded) {
        iframe.src = WIDGET;
        iframeLoaded = true;
      }
      unread = 0;
      bubble.innerHTML = iconClose;
      bubble.appendChild(badge);
      bubble.setAttribute("aria-label", "Close AthenTech Assistant");
    } else {
      panel.classList.remove("at-open");
      panel.style.display = "none";
      bubble.innerHTML = iconChat;
      bubble.appendChild(badge);
      bubble.setAttribute("aria-label", "Open AthenTech Assistant");
    }
    renderBadge();
  }

  bubble.addEventListener("click", function () {
    setOpen(!open);
  });
  btnClose.addEventListener("click", function () {
    setOpen(false);
  });
  btnMin.addEventListener("click", function () {
    setOpen(false);
  });

  /* unread from iframe when panel is closed */
  window.addEventListener("message", function (ev) {
    try {
      var data = ev.data || {};
      if (data && data.source === "athentech-widget" && data.type === "bot-message") {
        if (!open) {
          unread = Math.min(9, (unread || 0) + 1);
          renderBadge();
        }
      }
    } catch (e) {}
  });

  document.body.appendChild(panel);
  document.body.appendChild(bubble);
  renderBadge();
  /* bubble only — no auto-open */
})();
