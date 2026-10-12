"""Sahasra Guardian: per-client error log, plain-language classification, circuit breaker, read-only SQL guard.

Safe by design: it only observes, blocks, and recommends. It never changes client data or deploys code.
"""
import json
import os
import re
import threading
import time
from collections import defaultdict, deque

_LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
_LOG = os.path.join(_LOG_DIR, "guardian_events.jsonl")
_MAX_BYTES = 5 * 1024 * 1024
_lock = threading.Lock()
_recent = defaultdict(lambda: deque(maxlen=200))     # client -> events
_fail_times = defaultdict(lambda: deque(maxlen=20))  # client -> connection-failure timestamps
_open_until = {}                                     # client -> epoch when circuit closes
FAIL_LIMIT, FAIL_WINDOW, OPEN_SECONDS = 5, 120, 60

# (category, regex over the error text, plain message, safe action)
_RULES = [
    ("database_connection", r"login failed|08001|08s01|cannot open database|network-related|tcp provider|server does not exist|timeout expired|communication link|connection (is )?(closed|refused|reset)",
     "The client's database could not be reached or the login was rejected.", "Check the SQL Server is running and the stored login/password; retry in a minute."),
    ("schema_changed", r"invalid column name|invalid object name|ambiguous column|42s22|42s02",
     "A table or column the report needs is missing or renamed in this client's database.", "Open client diagnostics (refresh=true). Pin the correct column in config/clients/<DB>.json or disable that report and raise a support ticket."),
    ("query_timeout", r"query timeout|timeout|hyt00|hyt01",
     "The database took too long to answer.", "Retry with a shorter period (today / this week)."),
    ("licensing", r"activation code|license|expired|device",
     "A licensing or activation problem.", "Check the licence status and expiry in the admin panel."),
    ("llm_provider", r"groq|openai|rate.?limit|429|api key|model_decommissioned|overloaded|context length",
     "The AI language service failed or is rate-limited.", "Retry later; check the AI quota page in admin. Instant (menu) answers still work."),
    ("report_export", r"openpyxl|xlsx|reportlab|pdf|excel|memoryerror",
     "Building the Excel/PDF file failed.", "Retry once; if it repeats, try a shorter period and send the diagnostic package."),
]


def _clean(text, n=300):
    t = str(text or "")
    t = re.sub(r"(?i)(pwd|password|passwd|uid|user id)\s*=\s*[^;\s]+", r"\1=***", t)
    t = re.sub(r"\b\d{10}\b", "**********", t)           # phone numbers
    return t[:n]


def classify(error_text):
    low = str(error_text or "").lower()
    for cat, rx, msg, action in _RULES:
        if re.search(rx, low):
            return {"category": cat, "message": msg, "safe_action": action}
    return {"category": "unknown", "message": "An unexpected error occurred.",
            "safe_action": "Download the diagnostic package and send it to support. Nothing was changed in the client data."}


def record_event(client, area, error, extra=None):
    """client = database name. area = ask|excel|pdf|connection|selfcheck. Returns the classified event."""
    client = client or "unknown"
    cls = classify(error)
    ev = {"ts": time.strftime("%Y-%m-%d %H:%M:%S"), "client": client, "area": area,
          "error": _clean(error), **cls}
    if extra:
        ev["extra"] = _clean(extra, 200)
    with _lock:
        _recent[client].append(ev)
        try:
            os.makedirs(_LOG_DIR, exist_ok=True)
            if os.path.exists(_LOG) and os.path.getsize(_LOG) > _MAX_BYTES:
                os.replace(_LOG, _LOG + ".1")
            with open(_LOG, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(ev) + "\n")
        except Exception:
            pass
    if cls["category"] == "database_connection" and area == "connection":
        _note_connection_failure(client)
    return ev


def _note_connection_failure(client):
    now = time.time()
    with _lock:
        d = _fail_times[client]
        d.append(now)
        recent = [t for t in d if now - t <= FAIL_WINDOW]
        if len(recent) >= FAIL_LIMIT:
            _open_until[client] = now + OPEN_SECONDS


def circuit_open(client):
    """True while this client's DB is being failed fast (other clients unaffected)."""
    with _lock:
        until = _open_until.get(client or "unknown", 0)
    return time.time() < until


def status():
    out, now = [], time.time()
    with _lock:
        for client, evs in _recent.items():
            last = evs[-1] if evs else None
            counts = defaultdict(int)
            for e in evs:
                counts[e["category"]] += 1
            out.append({"client": client, "errors_recent": len(evs), "by_category": dict(counts),
                        "circuit_open": now < _open_until.get(client, 0), "last_error": last})
    out.sort(key=lambda r: (not r["circuit_open"], -r["errors_recent"]))
    return {"clients_with_errors": len(out), "clients": out}


def install(dbconn_module):
    """Wrap get_hospital_connection (call BEFORE other modules import it): fail fast per client + log failures."""
    orig = getattr(dbconn_module, "get_hospital_connection", None)
    if orig is None or getattr(orig, "_guardian", False):
        return

    def guarded(db_name=None, db_server=None, db_user=None, db_password=None, *a, **kw):
        key = db_name or "default"
        if circuit_open(key):
            record_event(key, "circuit", "circuit open: skipped this database for a minute to protect other clients")
            return None
        try:
            conn = orig(db_name, db_server, db_user, db_password, *a, **kw)
        except Exception as e:
            record_event(key, "connection", str(e))
            raise
        if conn is None:
            record_event(key, "connection", "connection returned None (login failed or server unreachable)")
        return conn
    guarded._guardian = True
    dbconn_module.get_hospital_connection = guarded


_BAD = re.compile(r"\b(insert|update|delete|drop|alter|create|truncate|exec|execute|merge|grant|revoke|backup|restore|shutdown|openrowset|opendatasource|bulk|waitfor|xp_\w*|sp_\w*)\b", re.I)


def is_safe_select(sql):
    """Read-only guard: one SELECT/CTE statement, no write/DDL/exec keywords, no SELECT ... INTO."""
    q = re.sub(r"--[^\n]*|/\*.*?\*/", " ", str(sql or ""), flags=re.S).strip().rstrip(";").strip()
    if not q:
        return False, "Empty query."
    if ";" in q:
        return False, "Only one statement is allowed."
    if not re.match(r"(?is)^(select|with)\b", q):
        return False, "Only SELECT queries are allowed."
    if _BAD.search(re.sub(r"'[^']*'", "''", q)):
        return False, "Only read-only SELECT is allowed."
    if re.search(r"(?is)\bselect\b.*\binto\b\s+[#@\w\[]", re.sub(r"'[^']*'", "''", q)) and not re.search(r"(?is)\binsert\b", q):
        return False, "SELECT ... INTO is not allowed."
    return True, ""
