/**
 * Sahasra AI Assistant — widget loader.
 * Drop-in replacement for the Zoho SalesIQ snippet. Creates a floating
 * chat bubble (bottom-right, matching Zoho's usual position) that opens
 * the real widget (sahasra_chat_widget.html) inside an iframe when clicked.
 *
 * IMPORTANT: update WIDGET_URL below to the real, live URL where
 * sahasra_chat_widget.html is actually hosted once a real domain exists.
 */
(function () {
  var WIDGET_URL = "https://YOUR_DOMAIN/widget_files/index.html"; // TODO: real domain

  var bubble = document.createElement("div");
  bubble.id = "sahasra-widget-bubble";
  bubble.innerHTML = "💬";
  bubble.style.cssText = [
    "position: fixed",
    "bottom: 20px",
    "right: 20px",
    "width: 60px",
    "height: 60px",
    "border-radius: 50%",
    "background: linear-gradient(135deg, #8B008B, #1e293b)",
    "color: white",
    "font-size: 26px",
    "display: flex",
    "align-items: center",
    "justify-content: center",
    "cursor: pointer",
    "box-shadow: 0 4px 12px rgba(0,0,0,0.25)",
    "z-index: 999998",
    "transition: transform 0.15s ease",
  ].join(";");
  bubble.onmouseenter = function () { bubble.style.transform = "scale(1.08)"; };
  bubble.onmouseleave = function () { bubble.style.transform = "scale(1)"; };

  var frameWrap = document.createElement("div");
  frameWrap.id = "sahasra-widget-frame-wrap";
  frameWrap.style.cssText = [
    "position: fixed",
    "bottom: 90px",
    "right: 20px",
    "width: 400px",
    "height: 620px",
    "max-width: calc(100vw - 40px)",
    "max-height: calc(100vh - 110px)",
    "border-radius: 16px",
    "overflow: hidden",
    "box-shadow: 0 8px 30px rgba(0,0,0,0.3)",
    "display: none",
    "z-index: 999999",
  ].join(";");

  var iframe = document.createElement("iframe");
  iframe.src = WIDGET_URL;
  iframe.style.cssText = "width: 100%; height: 100%; border: none;";
  frameWrap.appendChild(iframe);

  var isOpen = false;
  bubble.addEventListener("click", function () {
    isOpen = !isOpen;
    frameWrap.style.display = isOpen ? "block" : "none";
    bubble.innerHTML = isOpen ? "✕" : "💬";
  });

  document.body.appendChild(bubble);
  document.body.appendChild(frameWrap);
})();