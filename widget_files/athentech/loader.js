/**
 * AthenTech chat bubble — auto-opens gently on load
 * <script src="https://api.athentech.in/widget/athentech/loader.js" defer></script>
 */
(function () {
  if (document.getElementById("athentech-chat-bubble")) return;
  var WIDGET = "https://api.athentech.in/widget/athentech/index.html";
  try {
    var cfg = Object.assign({}, window.AthenTechChat || {});
    if (cfg.widget && /^https?:\/\//i.test(cfg.widget) && /\/widget\//i.test(cfg.widget)) WIDGET = String(cfg.widget);
  } catch (e) {}

  var style = document.createElement("style");
  style.textContent =
    "@keyframes at-bubble-in{from{opacity:0;transform:scale(.85) translateY(12px)}to{opacity:1;transform:scale(1) translateY(0)}}" +
    "@keyframes at-panel-in{from{opacity:0;transform:translateY(16px) scale(.98)}to{opacity:1;transform:translateY(0) scale(1)}}" +
    "#athentech-chat-bubble{animation:at-bubble-in .35s ease-out}" +
    "#athentech-chat-panel.at-open{display:block;animation:at-panel-in .3s ease-out}";
  document.head.appendChild(style);

  var ORANGE = "linear-gradient(135deg, #f97316, #ea580c)";
  var bubble = document.createElement("button");
  bubble.id = "athentech-chat-bubble";
  bubble.type = "button";
  bubble.setAttribute("aria-label", "Open AthenTech Assistant");
  bubble.innerHTML = '<svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/><path d="M8 9h8"/><path d="M8 13h5"/></svg>';
  bubble.style.cssText = "position:fixed;bottom:22px;right:22px;width:60px;height:60px;border-radius:50%;border:none;background:"+ORANGE+";color:#fff;display:flex;align-items:center;justify-content:center;cursor:pointer;box-shadow:0 10px 28px rgba(249,115,22,.4);z-index:2147483000;";

  var panel = document.createElement("div");
  panel.id = "athentech-chat-panel";
  panel.style.cssText = "position:fixed;bottom:96px;right:22px;width:420px;height:640px;max-width:calc(100vw - 20px);max-height:calc(100vh - 110px);border-radius:18px;overflow:hidden;box-shadow:0 20px 50px rgba(15,23,42,.22);border:1px solid #e2e8f0;background:#fff;z-index:2147483000;display:none;";

  var iframe = document.createElement("iframe");
  iframe.title = "AthenTech Assistant";
  iframe.src = "about:blank";
  iframe.setAttribute("allow", "clipboard-write");
  iframe.style.cssText = "width:100%;height:100%;border:0;display:block;background:#fff";
  panel.appendChild(iframe);

  var open = false;
  function setOpen(v) {
    open = v;
    if (open) {
      panel.classList.add("at-open");
      panel.style.display = "block";
      if (iframe.src === "about:blank") iframe.src = WIDGET;
    } else {
      panel.classList.remove("at-open");
      panel.style.display = "none";
    }
  }
  bubble.addEventListener("click", function () { setOpen(!open); });
  document.body.appendChild(panel);
  document.body.appendChild(bubble);

  // gentle auto-open once per page load
  setTimeout(function () { setOpen(true); }, 900);
})();
