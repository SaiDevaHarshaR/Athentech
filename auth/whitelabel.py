"""
White-label chatbot — per-client configuration + embed generation.

One row per LIS/HIS client (institution) in `whitelabel_configs`; the table
creates itself on first use, so there is no migration to run. Wired into
main.py with two lines (see bottom of this file).

Embed contract the widget must read from its URL / window.SahasraChat:
    label = normal | white
    client = <client_prefix>        (white only)
    mode   = b2c | b2b | admin      (white only)
    lang   = default language code
    langs  = comma list, only when several languages were selected
    site   = origin of the page that embeds the widget (optional)

Security notes
  * everything the public endpoint returns is safe to expose (branding, which
    modes are on, language list, feature flags). DB credentials, the B2C
    knowledge text and activation-code logic never leave the server.
  * the client id in an embed is NOT a secret and grants nothing: live data
    still needs a valid activation code, exactly like today.
  * "no Smart Report PDF" is a product-surface rule enforced by the widget and
    by the `smart_report_allowed()` check, not an access-control boundary.
"""

import html
import json
import os
import re
import time
from collections import defaultdict, deque
from datetime import datetime, date
from typing import List, Optional
from urllib.parse import urlencode, urlparse

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

MODES = ("b2c", "b2b", "admin")

LANGUAGES = {
    "en": "English", "hi": "Hindi", "te": "Telugu", "ta": "Tamil", "kn": "Kannada",
    "ml": "Malayalam", "mr": "Marathi", "bn": "Bengali", "gu": "Gujarati",
    "pa": "Punjabi", "ur": "Urdu", "or": "Odia",
}

_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
_BOOL_FIELDS = (
    "enabled", "b2c_enabled", "b2b_enabled", "admin_enabled", "smart_report_enabled",
    "idle_nudge_enabled", "preview_toast_enabled",
)
_TEXT_LIMITS = {
    "brand_name": 100,
    "welcome_message": 500,
    "b2b_notice": 500,
    "b2c_knowledge": 6000,
    "subtitle": 200,
    "footer_text": 300,
    "disclaimer_text": 500,
    "escalate_phone": 40,
    "escalate_message": 500,
    "idle_nudge_message": 500,
}
_DEFAULTS = {
    "enabled": 1, "default_mode": "b2c",
    "b2c_enabled": 1, "b2b_enabled": 0, "admin_enabled": 1, "smart_report_enabled": 0,
    "brand_name": "", "brand_logo_url": "", "primary_color": "", "welcome_message": "",
    "b2c_knowledge": "", "b2b_notice": "", "site_url": "", "languages": "en",
    # appearance (parity with normal chatbot settings)
    "subtitle": "",
    "secondary_color": "",
    "bg_color": "",
    "footer_text": "",
    "disclaimer_text": "",
    "width_px": 420,
    "height_px": 700,
    "max_history": 50,
    "session_timeout_min": 0,
    "preview_toast_enabled": 1,
    # escalate
    "escalate_phone": "",
    "escalate_message": "",
    # idle nudge
    "idle_nudge_enabled": 0,
    "idle_nudge_minutes": 3,
    "idle_nudge_message": "",
}

_DDL = """
IF OBJECT_ID('whitelabel_configs', 'U') IS NULL
CREATE TABLE whitelabel_configs (
    institution_id INT NOT NULL PRIMARY KEY,
    enabled INT NOT NULL DEFAULT 1,
    default_mode NVARCHAR(10) NOT NULL DEFAULT 'b2c',
    b2c_enabled INT NOT NULL DEFAULT 1,
    b2b_enabled INT NOT NULL DEFAULT 0,
    admin_enabled INT NOT NULL DEFAULT 1,
    smart_report_enabled INT NOT NULL DEFAULT 0,
    brand_name NVARCHAR(100) NULL,
    brand_logo_url NVARCHAR(500) NULL,
    primary_color NVARCHAR(20) NULL,
    welcome_message NVARCHAR(500) NULL,
    b2c_knowledge NVARCHAR(MAX) NULL,
    b2b_notice NVARCHAR(500) NULL,
    site_url NVARCHAR(500) NULL,
    languages NVARCHAR(200) NOT NULL DEFAULT 'en',
    updated_at NVARCHAR(40) NULL,
    updated_by NVARCHAR(100) NULL
)
"""

_table_ready = False


# ----------------------------------------------------------------------
# storage
# ----------------------------------------------------------------------

def _conn():
    from database.license_db import get_conn  # late import: keeps this module testable
    return get_conn()


def _row_to_dict(row) -> dict:
    return dict(row.items()) if hasattr(row, "items") else dict(row)


def _ensure_table(cur, conn):
    global _table_ready
    if _table_ready:
        return
    cur.execute(_DDL)
    conn.commit()
    _table_ready = True


def _bools(cfg: dict) -> dict:
    for f in _BOOL_FIELDS:
        cfg[f] = bool(int(cfg.get(f) or 0))
    return cfg


def get_config(institution_id: int) -> dict:
    conn = _conn()
    try:
        cur = conn.cursor()
        _ensure_table(cur, conn)
        cur.execute("SELECT * FROM whitelabel_configs WHERE institution_id = ?", (institution_id,))
        row = cur.fetchone()
    finally:
        conn.close()

    cfg = dict(_DEFAULTS)
    cfg["institution_id"] = institution_id
    cfg["configured"] = False
    if row:
        data = _row_to_dict(row)
        for key in _DEFAULTS:
            if data.get(key) is not None:
                cfg[key] = data[key]
        cfg["configured"] = True
    cfg["languages"] = [c for c in str(cfg["languages"]).split(",") if c in LANGUAGES] or ["en"]
    return _bools(cfg)


# ----------------------------------------------------------------------
# validation
# ----------------------------------------------------------------------

def normalize_site_url(url: str) -> str:
    """Returns scheme://host[:port] or raises ValueError. Used as an allow-list origin; never fetched."""
    url = (url or "").strip()
    if not url:
        return ""
    if len(url) > 500 or re.search(r"\s", url):
        raise ValueError("Site URL is invalid (too long or contains spaces).")
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc or not parsed.hostname:
        raise ValueError("Site URL must start with http:// or https:// and include a host.")
    if "@" in parsed.netloc:
        raise ValueError("Site URL must not contain credentials.")
    host = parsed.hostname or ""
    if not re.match(r"^[A-Za-z0-9]([A-Za-z0-9.-]*[A-Za-z0-9])?$", host):
        raise ValueError("Site URL has an invalid host name.")
    try:
        port = parsed.port
    except ValueError:
        raise ValueError("Site URL has an invalid port.")
    return f"{parsed.scheme}://{host.lower()}" + (f":{port}" if port else "")


def _clean_languages(langs) -> List[str]:
    if isinstance(langs, str):
        langs = [x for x in langs.split(",") if x]
    out = []
    for code in langs or []:
        code = str(code).strip().lower()
        if code not in LANGUAGES:
            raise ValueError(f"Unsupported language '{code}'.")
        if code not in out:
            out.append(code)
    if not out:
        raise ValueError("Select at least one language.")
    return out


def _validate(payload: dict, current: dict) -> dict:
    """Merges `payload` over `current` and validates the result. Returns the full cleaned config."""
    cfg = {k: current.get(k) for k in list(_DEFAULTS) + ["languages"]}
    cfg.update({k: v for k, v in payload.items() if k in _DEFAULTS})

    for f in _BOOL_FIELDS:
        cfg[f] = bool(cfg[f])

    for field, limit in _TEXT_LIMITS.items():
        value = str(cfg.get(field) or "").strip()
        if len(value) > limit:
            raise ValueError(f"{field.replace('_', ' ').capitalize()} is too long (max {limit} characters).")
        cfg[field] = value

    logo = str(cfg.get("brand_logo_url") or "").strip()
    if logo:
        p = urlparse(logo)
        if p.scheme != "https" or not p.netloc or len(logo) > 500 or re.search(r"\s", logo):
            raise ValueError("Logo URL must be a valid https:// link.")
    cfg["brand_logo_url"] = logo

    color = str(cfg.get("primary_color") or "").strip()
    if color and not _COLOR_RE.match(color):
        raise ValueError("Primary colour must look like #1a73e8.")
    cfg["primary_color"] = color

    cfg["site_url"] = normalize_site_url(cfg.get("site_url") or "")
    cfg["languages"] = _clean_languages(cfg.get("languages"))

    mode = str(cfg.get("default_mode") or "").lower()
    if mode not in MODES:
        raise ValueError("Default mode must be b2c, b2b or admin.")
    if cfg["enabled"] and not any(cfg[f"{m}_enabled"] for m in MODES):
        raise ValueError("Enable at least one mode.")
    if cfg["enabled"] and not cfg[f"{mode}_enabled"]:
        raise ValueError(f"Default mode '{mode}' is switched off — enable it or pick another default.")
    cfg["default_mode"] = mode
    return cfg


def save_config(institution_id: int, payload: dict, admin: str) -> dict:
    cfg = _validate(payload, get_config(institution_id))
    row = {k: (int(v) if k in _BOOL_FIELDS else v) for k, v in cfg.items() if k in _DEFAULTS}
    row["languages"] = ",".join(cfg["languages"])
    row["updated_at"] = datetime.utcnow().isoformat(timespec="seconds")
    row["updated_by"] = admin

    conn = _conn()
    try:
        cur = conn.cursor()
        _ensure_table(cur, conn)
        cur.execute("SELECT institution_id FROM whitelabel_configs WHERE institution_id = ?", (institution_id,))
        if cur.fetchone():
            cols = list(row)
            cur.execute(f"UPDATE whitelabel_configs SET {', '.join(c + ' = ?' for c in cols)} WHERE institution_id = ?",
                        tuple(row[c] for c in cols) + (institution_id,))
        else:
            cols = ["institution_id"] + list(row)
            cur.execute(f"INSERT INTO whitelabel_configs ({', '.join(cols)}) VALUES ({', '.join('?' for _ in cols)})",
                        (institution_id,) + tuple(row[c] for c in row))
        conn.commit()
    finally:
        conn.close()
    return get_config(institution_id)


# ----------------------------------------------------------------------
# embed generation (pure function — no I/O)
# ----------------------------------------------------------------------

_SAFE_URL = re.compile(r"^https?://[A-Za-z0-9._~:/?&=%+#-]+$")   # no quotes, $, backslash, <, >, spaces


def _php_value(v) -> str:
    if isinstance(v, (list, tuple)):
        return "[" + ", ".join(_php_value(x) for x in v) + "]"
    return "'" + str(v).replace("\\", "\\\\").replace("'", "\\'") + "'"


def build_snippets(cfg: dict, embed_url: str, loader_url: str) -> list:
    """
    Ready-to-paste code for the platform the client's developer uses.
    All inputs are validated beforehand (client id, mode, origin, URLs), so none of them can
    contain a quote, backslash or `$` — plain "..." literals are safe in every language below.
    """
    cfg_json = json.dumps(cfg, ensure_ascii=True).replace("</", "<\\/")
    pretty = json.dumps(cfg, ensure_ascii=True, indent=2).replace("</", "<\\/")
    pretty_ind = pretty.replace("\n", "\n    ")
    php_pairs = ",\n".join(f"    '{k}' => {_php_value(v)}" for k, v in cfg.items())
    L = html.escape(loader_url, quote=True)
    scripts = f'<script>window.SahasraChat = {cfg_json};</script>\n<script src="{L}" defer></script>'

    def s(id_, label, where, lang, code):
        return {"id": id_, "label": label, "where": where, "language": lang, "code": code}

    items = [
        s("html", "HTML", "Paste just before </body> on every page where the chat should appear.", "html", scripts),
        s("javascript", "JavaScript", "Add to your site's main .js file, or run it once after the page loads.", "javascript",
          f'''window.SahasraChat = {pretty};
(function () {{
  var s = document.createElement("script");
  s.src = "{loader_url}";
  s.defer = true;
  document.body.appendChild(s);
}})();'''),
        s("iframe", "iframe", "Paste where you want the chat box to sit on the page.", "html",
          f'<iframe src="{html.escape(embed_url, quote=True)}" title="Chat assistant"\n'
          f'        style="border:0;width:400px;height:640px;max-width:100%;" allow="clipboard-write"></iframe>'),
        s("react", "React", "Save as ChatWidget.jsx, then render <ChatWidget /> once, e.g. in App.jsx.", "jsx",
          f'''import {{ useEffect }} from "react";

export default function ChatWidget() {{
  useEffect(() => {{
    window.SahasraChat = {pretty_ind};
    const script = document.createElement("script");
    script.src = "{loader_url}";
    script.defer = true;
    document.body.appendChild(script);
    return () => {{
      script.remove();
      const bubble = document.getElementById("sahasra-widget-bubble");
      if (bubble && bubble.parentElement) bubble.parentElement.remove();
      ["sahasra-widget-preview", "sahasra-widget-frame-wrap"].forEach((id) => {{
        const el = document.getElementById(id);
        if (el) el.remove();
      }});
    }};
  }}, []);
  return null;
}}'''),
        s("nextjs", "Next.js", "Save as components/ChatWidget.jsx and render it once in app/layout.jsx (or pages/_app.js).", "jsx",
          f'''"use client";
import Script from "next/script";

export default function ChatWidget() {{
  return (
    <>
      <Script id="sahasra-config" strategy="afterInteractive">
        {{`window.SahasraChat = {cfg_json};`}}
      </Script>
      <Script src="{loader_url}" strategy="afterInteractive" />
    </>
  );
}}'''),
        s("angular", "Angular", "Paste into src/index.html just before </body>.", "html", scripts),
        s("vue", "Vue", "Put inside App.vue (the <template> can stay as it is).", "vue",
          f'''<script setup>
import {{ onMounted }} from "vue";

onMounted(() => {{
  window.SahasraChat = {pretty_ind};
  const script = document.createElement("script");
  script.src = "{loader_url}";
  script.defer = true;
  document.body.appendChild(script);
}});
</script>'''),
        s("wordpress", "WordPress", "Add to your theme's functions.php (Appearance → Theme File Editor), or use a child theme.", "php",
          f'''add_action('wp_footer', function () {{
    $cfg = [
{php_pairs}
    ];
    echo '<script>window.SahasraChat = ' . wp_json_encode($cfg) . ';</script>';
    echo '<script src="{L}" defer></script>';
}});'''),
        s("php", "PHP", "Paste into your shared footer file (e.g. footer.php) just before </body>.", "php",
          f'''<?php
$sahasra = [
{php_pairs}
];
?>
<script>window.SahasraChat = <?= json_encode($sahasra, JSON_UNESCAPED_SLASHES) ?>;</script>
<script src="{L}" defer></script>'''),
        s("python", "Python", "Flask: complete example. Django/Jinja: paste only the two <script> lines into base.html before </body>.", "python",
          f'''from flask import Flask, render_template_string

app = Flask(__name__)

PAGE = """<!doctype html>
<html>
<body>
  <h1>Your page</h1>
  <script>window.SahasraChat = {cfg_json};</script>
  <script src="{L}" defer></script>
</body>
</html>"""


@app.route("/")
def home():
    return render_template_string(PAGE)


if __name__ == "__main__":
    app.run()'''),
        s("java", "Java", "JSP: footer.jsp. Thymeleaf: templates/fragments/footer.html. Paste just before </body>.", "html", scripts),
        s("dotnet", ".NET (C#)", "Paste into Views/Shared/_Layout.cshtml just before </body>.", "html", scripts),
        s("node", "Node.js", "Paste into your layout/footer partial (e.g. views/partials/footer.ejs) just before </body>.", "html", scripts),
        s("builders", "Wix / Shopify / Others", "Add as custom code in the footer / 'before </body>' section of the site settings.", "html", scripts),
        s("android", "Android (Kotlin)", "Opens the chat full-screen in an Activity. Add the INTERNET permission to AndroidManifest.xml.", "kotlin",
          f'''// AndroidManifest.xml:  <uses-permission android:name="android.permission.INTERNET" />
val webView = findViewById<WebView>(R.id.chatWebView)
webView.settings.javaScriptEnabled = true
webView.settings.domStorageEnabled = true
webView.loadUrl("{embed_url}")'''),
        s("flutter", "Flutter", "Add webview_flutter to pubspec.yaml, then show the widget on any screen.", "dart",
          f'''import 'package:webview_flutter/webview_flutter.dart';

final controller = WebViewController()
  ..setJavaScriptMode(JavaScriptMode.unrestricted)
  ..loadRequest(Uri.parse('{embed_url}'));

// inside build():
// WebViewWidget(controller: controller)'''),
        s("ios", "iOS (Swift)", "Opens the chat full-screen in a view controller.", "swift",
          f'''import WebKit

let webView = WKWebView(frame: view.bounds)
view.addSubview(webView)
webView.load(URLRequest(url: URL(string: "{embed_url}")!))'''),
    ]
    order = ["html", "javascript", "java", "python", "dotnet", "php", "node", "wordpress", "react", "nextjs",
             "angular", "vue", "iframe", "builders", "android", "flutter", "ios"]
    return sorted(items, key=lambda x: order.index(x["id"]))


def build_embed(*, label: str, widget_url: str, loader_url: str, client_prefix: Optional[str] = None,
                mode: Optional[str] = None, languages=None, default_lang: Optional[str] = None,
                site_url: Optional[str] = None) -> dict:
    if label not in ("normal", "white"):
        raise ValueError("Label must be 'normal' or 'white'.")
    if label == "white":
        if not client_prefix or not re.match(r"^[A-Za-z0-9_-]{1,50}$", client_prefix):
            raise ValueError("A valid client is required for the white label.")
        if mode not in MODES:
            raise ValueError("Mode must be b2c, b2b or admin.")
    for u in (widget_url, loader_url):
        if not _SAFE_URL.match(u):
            raise ValueError("The widget/loader URL in the server .env contains unsupported characters.")

    # Chat language (optional, API only — the admin panel no longer offers it): English unless asked otherwise.
    langs = _clean_languages(languages or ["en"])
    default_lang = (default_lang or langs[0]).lower()
    if default_lang not in langs:
        raise ValueError("The default language must be one of the selected languages.")
    site = normalize_site_url(site_url) if site_url else ""
    show_lang = default_lang != "en" or len(langs) > 1

    def make_params(lang: str, with_switcher: bool) -> dict:
        p = {"label": label}
        if label == "white":
            p["client"], p["mode"] = client_prefix, mode
        if show_lang:
            p["lang"] = lang
        if with_switcher and len(langs) > 1:
            p["langs"] = ",".join(langs)
        if site:
            p["site"] = site
        return p

    def url_for(params: dict) -> str:
        return widget_url + ("&" if "?" in widget_url else "?") + urlencode(params)

    params = make_params(default_lang, True)
    embed_url = url_for(params)
    cfg = {k: params[k] for k in ("label", "client", "mode", "lang", "site") if k in params}
    if len(langs) > 1:
        cfg["langs"] = langs

    snippets = build_snippets(cfg, embed_url, loader_url)
    return {
        "embed_url": embed_url,
        "snippets": snippets,
        "script_snippet": {x["id"]: x for x in snippets}["html"]["code"],     # kept for older callers
        "iframe_snippet": {x["id"]: x for x in snippets}["iframe"]["code"],
        "per_language": [{"lang": c, "name": LANGUAGES[c], "embed_url": url_for(make_params(c, False))} for c in langs],
        "params": params,
    }


def _public_urls():
    widget_url = os.environ.get("PUBLIC_WIDGET_URL", "").strip()
    if not widget_url:
        raise HTTPException(500, "PUBLIC_WIDGET_URL is not set in the backend .env — set it to the full widget page URL.")
    p = urlparse(widget_url)
    loader_url = os.environ.get("PUBLIC_LOADER_URL", "").strip() or f"{p.scheme}://{p.netloc}/widget-loader.js"
    return widget_url, loader_url


# ----------------------------------------------------------------------
# helpers other parts of the backend can call
# ----------------------------------------------------------------------

def _institutions() -> list:
    from auth.license_service import list_institutions
    return list_institutions()


def find_institution_by_prefix(prefix: str) -> Optional[dict]:
    prefix = (prefix or "").strip().upper()
    for inst in _institutions():
        if str(inst.get("client_prefix", "")).upper() == prefix:
            return inst
    return None


def smart_report_allowed(client_prefix: Optional[str]) -> bool:
    """False for a white-label client that has not been granted Smart Report PDFs; True when no client given."""
    if not client_prefix:
        return True
    inst = find_institution_by_prefix(client_prefix)
    return bool(inst) and get_config(int(inst["id"]))["smart_report_enabled"]


def get_b2c_knowledge(client_prefix: str) -> str:
    """Admin-written FAQ / info text to add to the LLM context in B2C mode (server-side only)."""
    inst = find_institution_by_prefix(client_prefix)
    if not inst:
        return ""
    return get_config(int(inst["id"]))["b2c_knowledge"] or ""


# ----------------------------------------------------------------------
# B2C chat: public, unauthenticated -> strict limits (it spends LLM credits)
# ----------------------------------------------------------------------

_B2C_PER_MIN = int(os.environ.get("WL_B2C_PER_MIN", "10"))        # questions per minute per visitor IP
_B2C_DAILY_CAP = int(os.environ.get("WL_B2C_DAILY_CAP", "3000"))  # questions per day per client
_B2C_MAX_QUESTION = 500
_B2C_MAX_HISTORY = 6
_b2c_hits = defaultdict(deque)   # (ip, client) -> request timestamps
_b2c_daily = {}                  # (client, date) -> count   (in-process; resets on restart)


def _throttle(ip: str, client: str):
    """Returns a user-facing message when a limit is hit, else None (and counts the request)."""
    now = time.time()
    q = _b2c_hits[(ip, client)]
    while q and now - q[0] > 60:
        q.popleft()
    if len(q) >= _B2C_PER_MIN:
        return "You are sending messages too quickly. Please wait a moment."
    key = (client, date.today())
    for k in [k for k in _b2c_daily if k[1] != date.today()]:
        del _b2c_daily[k]
    if _b2c_daily.get(key, 0) >= _B2C_DAILY_CAP:
        return "This assistant has reached its daily limit. Please try again tomorrow or contact us directly."
    q.append(now)
    _b2c_daily[key] = _b2c_daily.get(key, 0) + 1
    return None


def build_b2c_messages(brand: str, knowledge: str, lang: str, question: str, history) -> list:
    """[(role, text), ...] with role in system|user|assistant. Pure function."""
    language = LANGUAGES.get((lang or "en").lower(), "English")
    system = (
        f"You are the virtual assistant for {brand}, a healthcare / diagnostics provider, talking to a member of the public.\n"
        "Answer questions about the provider's services, locations, timings and booking using ONLY the information below, "
        "plus general, non-diagnostic health information.\n"
        "If the answer is not in the information, say you do not have that detail and suggest contacting the provider directly. "
        "Never invent prices, timings, phone numbers or addresses.\n"
        "You cannot see any patient records or reports in this chat. Never ask for or accept personal medical details. "
        "Do not diagnose or recommend treatment; for an emergency tell the person to call their local emergency number.\n"
        f"Reply in {language}. Keep answers short (under 120 words).\n\n"
        f"INFORMATION ABOUT {brand.upper()}:\n{knowledge.strip() or '(none provided)'}"
    )
    msgs = [("system", system)]
    for turn in list(history or [])[-_B2C_MAX_HISTORY:]:
        role = "assistant" if getattr(turn, "role", "") == "assistant" else "user"
        msgs.append((role, str(getattr(turn, "content", ""))[:600]))
    msgs.append(("user", question))
    return msgs


class ChatTurn(BaseModel):
    role: str
    content: str


class WhiteAskRequest(BaseModel):
    client: str
    question: str
    lang: str = "en"
    chat_history: List[ChatTurn] = []


# ----------------------------------------------------------------------
# routes
# ----------------------------------------------------------------------

class WhiteLabelConfigRequest(BaseModel):
    enabled: Optional[bool] = None
    default_mode: Optional[str] = None
    b2c_enabled: Optional[bool] = None
    b2b_enabled: Optional[bool] = None
    admin_enabled: Optional[bool] = None
    smart_report_enabled: Optional[bool] = None
    brand_name: Optional[str] = None
    brand_logo_url: Optional[str] = None
    primary_color: Optional[str] = None
    welcome_message: Optional[str] = None
    b2c_knowledge: Optional[str] = None
    b2b_notice: Optional[str] = None
    site_url: Optional[str] = None
    languages: Optional[List[str]] = None


class EmbedRequest(BaseModel):
    label: str
    institution_id: Optional[int] = None
    mode: Optional[str] = None
    url: Optional[str] = None
    languages: List[str] = ["en"]
    default_lang: Optional[str] = None


def build_router(require_admin, log_admin_action) -> APIRouter:
    router = APIRouter()

    def _institution_or_404(institution_id: int) -> dict:
        for inst in _institutions():
            if int(inst["id"]) == institution_id:
                return inst
        raise HTTPException(404, "Client not found.")

    @router.get("/admin/whitelabel/clients")
    def wl_clients(admin: str = Depends(require_admin)):
        return {"status": "success", "clients": [
            {"id": i["id"], "name": i.get("name"), "client_prefix": i.get("client_prefix"),
             "type": i.get("type"), "status": i.get("status")} for i in _institutions()
        ]}

    @router.get("/admin/whitelabel/{institution_id}")
    def wl_get(institution_id: int, admin: str = Depends(require_admin)):
        inst = _institution_or_404(institution_id)
        return {"status": "success", "client": {"id": inst["id"], "name": inst.get("name"),
                                                 "client_prefix": inst.get("client_prefix"), "type": inst.get("type")},
                "config": get_config(institution_id), "languages": LANGUAGES}

    @router.put("/admin/whitelabel/{institution_id}")
    def wl_save(institution_id: int, req: WhiteLabelConfigRequest, admin: str = Depends(require_admin)):
        inst = _institution_or_404(institution_id)
        try:
            cfg = save_config(institution_id, req.model_dump(exclude_unset=True), admin)
        except ValueError as e:
            raise HTTPException(400, str(e))
        log_admin_action(admin, "Updated white-label settings", inst.get("name", str(institution_id)),
                         meta={"changes": [k for k in req.model_dump(exclude_unset=True) if k != "b2c_knowledge"]})
        return {"status": "success", "config": cfg}

    @router.post("/admin/embed")
    def wl_embed(req: EmbedRequest, admin: str = Depends(require_admin)):
        widget_url, loader_url = _public_urls()
        client_prefix = mode = None
        if req.label == "white":
            if req.institution_id is None:
                raise HTTPException(400, "Choose a client for the white label.")
            inst = _institution_or_404(req.institution_id)
            cfg = get_config(req.institution_id)
            mode = (req.mode or cfg["default_mode"]).lower()
            if not cfg["configured"] or not cfg["enabled"]:
                raise HTTPException(400, "Save and enable this client's white-label settings before generating an embed.")
            if mode in MODES and not cfg[f"{mode}_enabled"]:
                raise HTTPException(400, f"Mode '{mode}' is switched off for this client — enable it and save first.")
            client_prefix = inst.get("client_prefix")
        try:
            result = build_embed(label=req.label, widget_url=widget_url, loader_url=loader_url,
                                 client_prefix=client_prefix, mode=mode, languages=req.languages,
                                 default_lang=req.default_lang, site_url=req.url)
        except ValueError as e:
            raise HTTPException(400, str(e))
        return {"status": "success", **result}

    @router.get("/public/whitelabel-config")
    def wl_public(client: str = Query(..., min_length=1, max_length=50)):
        """Called by the widget on load. Returns branding + switches only — nothing sensitive."""
        inst = find_institution_by_prefix(client)
        if not inst or str(inst.get("status", "Active")) != "Active":
            raise HTTPException(404, "Unknown client.")
        cfg = get_config(int(inst["id"]))
        if not cfg["configured"] or not cfg["enabled"]:
            raise HTTPException(404, "This chatbot is not available.")
        return {
            "status": "success", "label": "white", "client": inst.get("client_prefix"),
            "brand": {"name": cfg["brand_name"] or inst.get("name"), "logo_url": cfg["brand_logo_url"],
                      "primary_color": cfg["primary_color"], "welcome_message": cfg["welcome_message"]},
            "modes": {m: cfg[f"{m}_enabled"] for m in MODES},
            "default_mode": cfg["default_mode"], "languages": cfg["languages"],
            "features": {"smart_report": cfg["smart_report_enabled"]},
            "b2b_notice": cfg["b2b_notice"], "site_url": cfg["site_url"],
        }

    @router.post("/public/whitelabel-ask")
    def wl_ask(req: WhiteAskRequest, request: Request):
        """B2C mode: one LLM call, no tools, no database. Public, so it is throttled."""
        inst = find_institution_by_prefix(req.client)
        if not inst or str(inst.get("status", "Active")) != "Active":
            return {"status": "error", "answer": "This chat is not available."}
        cfg = get_config(int(inst["id"]))
        if not (cfg["configured"] and cfg["enabled"] and cfg["b2c_enabled"]):
            return {"status": "error", "answer": "This chat is not available."}

        question = (req.question or "").strip()
        if not question:
            return {"status": "error", "answer": "Please type a question."}
        if len(question) > _B2C_MAX_QUESTION:
            return {"status": "error", "answer": f"Please keep your question under {_B2C_MAX_QUESTION} characters."}

        ip = request.client.host if request.client else "unknown"
        limited = _throttle(ip, str(inst.get("client_prefix")).upper())
        if limited:
            return {"status": "error", "answer": limited}

        try:
            from agent.agent import _get_provider_chain, _invoke_with_retry
            try:
                from agent.agent import check_input
                ok, msg = check_input(question)
                if not ok:
                    return {"status": "success", "answer": msg}
            except ImportError:
                pass
            chain = _get_provider_chain()
            if not chain:
                return {"status": "error", "answer": "The assistant is temporarily unavailable."}
            name, llm = chain[0]
            try:
                llm = llm.bind(max_tokens=450)
            except Exception:
                pass

            from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
            kinds = {"system": SystemMessage, "user": HumanMessage, "assistant": AIMessage}
            msgs = [kinds[r](content=t) for r, t in build_b2c_messages(
                cfg["brand_name"] or inst.get("name") or "this provider", cfg["b2c_knowledge"], req.lang,
                question, req.chat_history)]
            resp = _invoke_with_retry(llm, msgs, retries=0, current_provider=name)
            text = (resp.content if hasattr(resp, "content") else str(resp or "")).strip() if resp else ""
            if not text:
                return {"status": "error", "answer": "Sorry, I could not answer that right now. Please try again."}
            return {"status": "success", "answer": text}
        except Exception as e:
            print(f"[whitelabel] b2c answer failed: {type(e).__name__}: {e}")
            return {"status": "error", "answer": "Sorry, something went wrong. Please try again."}

    return router


# --- hook for main.py (put at the very bottom, above any `if __name__` block) -------------
#   from auth.whitelabel import build_router as build_whitelabel_router
#   app.include_router(build_whitelabel_router(require_admin, _log_admin_action))