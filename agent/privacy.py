"""Patient privacy: phone masking by role, a lookup audit trail, a refused-question log, and retention (auto-delete).
Local SQLite only (logs/privacy.db). Never touches client databases."""
import hashlib
import json
import os
import re
import sqlite3
import threading
from datetime import datetime, timedelta, timezone

_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
_DB = os.environ.get("SAHASRA_PRIVACY_DB") or os.path.join(_DIR, "privacy.db")
_CFG = os.path.join(_DIR, "privacy.json")
_LOCK = threading.Lock()
_SCHEMA = """
CREATE TABLE IF NOT EXISTS lookups(id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, client TEXT, role TEXT, kind TEXT, question TEXT);
CREATE TABLE IF NOT EXISTS refused(id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, client TEXT, reason TEXT, question TEXT);
CREATE INDEX IF NOT EXISTS ix_l_ts ON lookups(ts); CREATE INDEX IF NOT EXISTS ix_r_ts ON refused(ts);
"""
DEFAULTS = {"chat_days": 90, "audit_days": 365, "refused_days": 90, "auto_purge": True, "mask_roles_full": "admin,reception"}

_PHONE = re.compile(r"(?<!\d)(?<!\d,)(?<!\.)(?:\+?91[\s-]?|0)?([6-9]\d{9})(?!\d|,\d|\.\d)")
_UHID = re.compile(r"\b(?:uhid|mr\s*no|mrn|patient\s*id|reg(?:istration)?\s*no)\W*[a-z]*\d{4,}\b|\b[a-z]{1,5}\d{6,}\b", re.I)
_LOOKUP = re.compile(r"\b(phone|mobile|contact|address|history|details?|record|reports?|bills?)\b.{0,25}\b(of|for)\b.{0,30}\b(patient|mr|mrs|ms)\b|\bpatient\s+(named|called|name)\b|\bphone number of\b", re.I)


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _conn():
    os.makedirs(_DIR, exist_ok=True)
    c = sqlite3.connect(_DB, timeout=5)
    c.executescript(_SCHEMA)
    return c


def get_cfg():
    try:
        with open(_CFG, encoding="utf-8") as f:
            d = json.load(f)
    except Exception:
        d = {}
    out = dict(DEFAULTS)
    out.update({k: d[k] for k in DEFAULTS if k in d})
    return out


def set_cfg(d):
    cur = get_cfg()
    for k in ("chat_days", "audit_days", "refused_days"):
        if k in d:
            v = int(d[k])
            if not 7 <= v <= 3650:
                raise ValueError("Days must be between 7 and 3650.")
            cur[k] = v
    if "auto_purge" in d:
        cur["auto_purge"] = bool(d["auto_purge"])
    if "mask_roles_full" in d:
        cur["mask_roles_full"] = ",".join(sorted({r.strip().lower() for r in str(d["mask_roles_full"]).split(",") if r.strip()}))
    os.makedirs(_DIR, exist_ok=True)
    with open(_CFG, "w", encoding="utf-8") as f:
        json.dump(cur, f)
    return cur


_PHONE2 = re.compile(r"(?<!\d)(?:\+?91[\s-]?)?([6-9]\d{4})[\s-](\d{5})(?!\d)")


def mask_phones(text):
    """9876543210 -> ******3210 (also +91 and '98765 43210' forms)."""
    try:
        if not isinstance(text, str):
            return text
        text = _PHONE.sub(lambda m: "******" + m.group(1)[-4:], text)
        return _PHONE2.sub(lambda m: "******" + m.group(2)[-4:], text)
    except Exception:
        return text


def mask_for_role(text, role):
    full = {r.strip() for r in get_cfg()["mask_roles_full"].split(",")}
    return text if str(role or "").lower() in full else mask_phones(text)


def _safe_q(q):
    return _PHONE.sub(lambda m: "******" + m.group(1)[-4:], str(q or ""))[:300]


def audit_lookup(client, role, question):
    """Records patient-specific lookups (UHID, phone, 'details of patient ...'). Returns the kind or None."""
    try:
        q = str(question or "")
        kind = "phone" if _PHONE.search(q) else "uhid" if _UHID.search(q) else "patient" if _LOOKUP.search(q) else None
        if not kind:
            return None
        with _LOCK:
            c = _conn()
            try:
                c.execute("INSERT INTO lookups(ts,client,role,kind,question) VALUES(?,?,?,?,?)",
                          (_now().isoformat(timespec="seconds"), str(client or "")[:40], str(role or "")[:20], kind, _safe_q(q)))
                c.commit()
            finally:
                c.close()
        return kind
    except Exception:
        return None


def log_refused(question, reason="", client=""):
    try:
        with _LOCK:
            c = _conn()
            try:
                c.execute("INSERT INTO refused(ts,client,reason,question) VALUES(?,?,?,?)",
                          (_now().isoformat(timespec="seconds"), str(client or "")[:40], str(reason or "")[:80], _safe_q(question)))
                c.commit()
            finally:
                c.close()
    except Exception:
        pass


def overview():
    with _LOCK:
        c = _conn()
        try:
            c.row_factory = sqlite3.Row
            lk = [dict(r) for r in c.execute("SELECT ts,client,role,kind,question FROM lookups ORDER BY id DESC LIMIT 50")]
            rf = [dict(r) for r in c.execute("SELECT ts,client,reason,question FROM refused ORDER BY id DESC LIMIT 50")]
            n = {"lookups": c.execute("SELECT COUNT(*) FROM lookups").fetchone()[0], "refused": c.execute("SELECT COUNT(*) FROM refused").fetchone()[0]}
        finally:
            c.close()
    return {"config": get_cfg(), "counts": n, "lookups": lk, "refused": rf}


def purge(force=False):
    """Deletes old rows per the retention settings. Returns counts."""
    cfg = get_cfg()
    if not force and not cfg["auto_purge"]:
        return {"skipped": True}
    out = {}
    with _LOCK:
        c = _conn()
        try:
            for tbl, days in (("lookups", cfg["audit_days"]), ("refused", cfg["refused_days"])):
                cut = (_now() - timedelta(days=days)).isoformat(timespec="seconds")
                out[tbl] = c.execute("DELETE FROM %s WHERE ts < ?" % tbl, (cut,)).rowcount
            c.commit()
        finally:
            c.close()
    try:                                       # answer review log (questions + short previews of low-confidence answers)
        from agent import answer_log as al
        cut = (_now() - timedelta(days=cfg["chat_days"])).isoformat(timespec="seconds")
        c = al._conn()
        try:
            out["answer_log"] = c.execute("DELETE FROM answer_log WHERE ts < ? AND (vote IS NULL OR resolved=1 OR ts < ?)",
                                          (cut, (_now() - timedelta(days=cfg["chat_days"] * 2)).isoformat(timespec="seconds"))).rowcount
            c.commit()
        finally:
            c.close()
    except Exception as e:
        out["answer_log"] = "skipped: " + type(e).__name__
    return out


_last = {"day": ""}


def tick():
    """Called every minute by the scheduler: one purge a day at 02:40 server time."""
    try:
        n = datetime.now()
        if n.strftime("%H:%M") == "02:40" and _last["day"] != n.strftime("%Y-%m-%d"):
            _last["day"] = n.strftime("%Y-%m-%d")
            purge()
    except Exception:
        pass
