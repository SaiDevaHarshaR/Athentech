

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
  var WIDGET_URL = "http://192.168.0.163:81/widget_files/index.html"; // TODO: real domain

  var bubble = document.createElement("div");
  bubble.id = "sahasra-widget-bubble";
  bubble.innerHTML = "💬";
  bubble.style.cssText = [
    "position: fixed",
    "bottom: 20px",
    "right: 20px",
    "width: 64px",
    "height: 64px",
    "border-radius: 50%",
    "background: linear-gradient(135deg, #8B008B, #1e293b)",
    "color: white",
    "font-size: 28px",
    "display: flex",
    "align-items: center",
    "justify-content: center",
    "cursor: pointer",
    "box-shadow: 0 4px 16px rgba(0,0,0,0.3)",
    "z-index: 999998",
    "transition: transform 0.2s cubic-bezier(0.34, 1.56, 0.64, 1), box-shadow 0.2s ease",
    "animation: sahasra-bubble-pop 0.4s cubic-bezier(0.34, 1.56, 0.64, 1)",
  ].join(";");
  bubble.onmouseenter = function () {
    bubble.style.transform = "scale(1.1)";
    bubble.style.boxShadow = "0 6px 20px rgba(0,0,0,0.35)";
  };
  bubble.onmouseleave = function () {
    bubble.style.transform = "scale(1)";
    bubble.style.boxShadow = "0 4px 16px rgba(0,0,0,0.3)";
  };

  var style = document.createElement("style");
  style.textContent =
    "@keyframes sahasra-bubble-pop { 0% { transform: scale(0); opacity: 0; } 60% { transform: scale(1.15); opacity: 1; } 100% { transform: scale(1); } }" +
    "@keyframes sahasra-frame-open { 0% { transform: translateY(20px) scale(0.95); opacity: 0; } 100% { transform: translateY(0) scale(1); opacity: 1; } }";
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
    "border-radius: 16px",
    "overflow: hidden",
    "box-shadow: 0 10px 40px rgba(0,0,0,0.35)",
    "display: none",
    "z-index: 999999",
    "animation: sahasra-frame-open 0.25s cubic-bezier(0.34, 1.56, 0.64, 1)",
  ].join(";");

  var iframe = document.createElement("iframe");
  iframe.src = WIDGET_URL;
  iframe.style.cssText = "width: 100%; height: 100%; border: none;";
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
    '<div style="width:24px; height:24px; border-radius:50%; background:linear-gradient(135deg,#8B008B,#1e293b); flex-shrink:0; display:flex; align-items:center; justify-content:center; font-size:12px; color:white; font-weight:700;">AI</div>' +
    '<div style="flex:1; min-width:0;">' +
    '<div style="font-size:11px; font-weight:700; color:#64748b; margin-bottom:2px;">Sahasra AI Assistant</div>' +
    '<div id="sahasra-preview-text" style="font-size:13px; color:#1e293b; line-height:1.4;"></div>' +
    '</div>' +
    '<div style="color:#94a3b8; font-size:14px; flex-shrink:0;" onclick="event.stopPropagation(); document.getElementById(\'sahasra-widget-preview\').style.display=\'none\';">✕</div>' +
    '</div>';
  preview.addEventListener("click", function () {
    preview.style.display = "none";
    isOpen = true;
    frameWrap.style.display = "block";
    bubble.innerHTML = "✕";
  });

  // Listens for the widget (inside the iframe) posting a message whenever
  // a new bot reply arrives — only shows the preview while the widget is
  // closed, since an open widget means the person is already looking at it.
  window.addEventListener("message", function (event) {
    if (event.data && event.data.type === "sahasra-new-message" && !isOpen) {
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
    bubble.innerHTML = isOpen ? "✕" : "💬";
    if (isOpen) {
      badge.style.display = "none";
      preview.style.display = "none";
    }
  });

  document.body.appendChild(bubbleWrap);
  document.body.appendChild(preview);
  document.body.appendChild(frameWrap);
})();