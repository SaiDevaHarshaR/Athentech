"""Answer log for the review queue, 👍/👎 feedback and 'how was this calculated'.

Local SQLite file (logs/answer_review.db). Never touches client LIS databases or the
admin database. Stores metadata only: a masked question, the score and reasons, the
read-only SQL the AI ran, and a short masked preview of answers that were flagged.
Never raises: logging must not break answering.
"""
import json
import os
import re
import sqlite3
import threading
import time
from datetime import datetime, timedelta, timezone

_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
_DB = os.environ.get("SAHASRA_ANSWER_DB") or os.path.join(_DIR, "answer_review.db")
_LOCK = threading.Lock()
RETAIN_DAYS = int(os.getenv("SAHASRA_ANSWER_RETAIN_DAYS", "90") or 90)
MAX_ROWS = 20000

_SCHEMA = """
CREATE TABLE IF NOT EXISTS answer_log(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts TEXT NOT NULL, client TEXT NOT NULL, role TEXT, question TEXT, source TEXT,
  score INTEGER, ok INTEGER, reasons TEXT, sql_json TEXT, tables_json TEXT, matched TEXT,
  preview TEXT, vote TEXT, vote_note TEXT, voted_ts TEXT,
  resolved INTEGER NOT NULL DEFAULT 0, resolve_note TEXT, resolved_ts TEXT);
CREATE INDEX IF NOT EXISTS ix_al_ts ON answer_log(ts);
CREATE INDEX IF NOT EXISTS ix_al_client ON answer_log(client, ts);
"""


def _clean(text, n=300):
    t = str(text or "")
    t = re.sub(r"(?i)(pwd|password|passwd|uid|user id)\s*=\s*[^;\s]+", r"\1=***", t)
    t = re.sub(r"\b\d{10}\b", "**********", t)            # phone numbers
    return t[:n]


def _conn():
    os.makedirs(os.path.dirname(_DB), exist_ok=True)
    c = sqlite3.connect(_DB, timeout=5)
    c.row_factory = sqlite3.Row
    c.executescript(_SCHEMA)
    return c


def log_answer(client, role, question, answer, conf, explain):
    """Returns the new answer id, or None. conf/explain may be None."""
    try:
        conf = conf or {}
        explain = explain or {}
        low = conf.get("ok") is False
        preview = _clean(answer, 300) if low else None
        with _LOCK:
            c = _conn()
            try:
                cur = c.execute(
                    "INSERT INTO answer_log(ts,client,role,question,source,score,ok,reasons,sql_json,"
                    "tables_json,matched,preview) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                    (datetime.now(timezone.utc).replace(tzinfo=None).isoformat(timespec="seconds"), str(client or "unknown"), role,
                     _clean(question, 400), conf.get("source") or explain.get("source"),
                     conf.get("score"), None if conf.get("ok") is None else int(bool(conf.get("ok"))),
                     json.dumps(conf.get("reasons") or []),
                     json.dumps([_clean(q, 1500) for q in (explain.get("queries") or [])][:5]),
                     json.dumps(explain.get("tables") or []),
                     _clean(explain.get("matched"), 120), preview))
                new_id = cur.lastrowid
                if new_id % 200 == 0:
                    _prune(c)
                c.commit()
                return new_id
            finally:
                c.close()
    except Exception:
        return None


def _prune(c):
    cutoff = (datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=RETAIN_DAYS)).isoformat(timespec="seconds")
    c.execute("DELETE FROM answer_log WHERE ts < ?", (cutoff,))
    c.execute("DELETE FROM answer_log WHERE id NOT IN (SELECT id FROM answer_log ORDER BY id DESC LIMIT ?)",
              (MAX_ROWS,))


def set_vote(answer_id, client, vote, note=None):
    """Only the institution that received the answer may vote on it. Returns True if saved."""
    try:
        if vote not in ("up", "down"):
            return False
        with _LOCK:
            c = _conn()
            try:
                cur = c.execute(
                    "UPDATE answer_log SET vote=?, vote_note=?, voted_ts=? "
                    "WHERE id=? AND client=?",
                    (vote, _clean(note, 300) if note else None,
                     datetime.now(timezone.utc).replace(tzinfo=None).isoformat(timespec="seconds"), int(answer_id), str(client)))
                c.commit()
                return cur.rowcount == 1
            finally:
                c.close()
    except Exception:
        return False


def attach_preview(answer_id, client, answer):
    """When a user votes 👎 on a 'confident' answer, keep a short masked preview for review."""
    try:
        with _LOCK:
            c = _conn()
            try:
                c.execute("UPDATE answer_log SET preview=? WHERE id=? AND client=? AND preview IS NULL",
                          (_clean(answer, 300), int(answer_id), str(client)))
                c.commit()
            finally:
                c.close()
    except Exception:
        pass


def _row(r):
    d = dict(r)
    for k in ("reasons", "sql_json", "tables_json"):
        try:
            d[k] = json.loads(d.get(k) or "[]")
        except Exception:
            d[k] = []
    return d


def list_rows(view="open", client=None, limit=50, offset=0):
    where, args = [], []
    if view == "open":           # needs a human: flagged low or thumbs-down, not yet resolved
        where.append("(ok = 0 OR vote = 'down') AND resolved = 0")
    elif view == "down":
        where.append("vote = 'down'")
    elif view == "low":
        where.append("ok = 0")
    elif view == "up":
        where.append("vote = 'up'")
    elif view == "resolved":
        where.append("resolved = 1")
    if client:
        where.append("client = ?")
        args.append(str(client))
    sql = "SELECT * FROM answer_log" + (" WHERE " + " AND ".join(where) if where else "")
    sql += " ORDER BY id DESC LIMIT ? OFFSET ?"
    args += [max(1, min(int(limit), 200)), max(0, int(offset))]
    with _LOCK:
        c = _conn()
        try:
            return [_row(r) for r in c.execute(sql, args).fetchall()]
        finally:
            c.close()


def stats(days=7):
    since = (datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)).isoformat(timespec="seconds")
    with _LOCK:
        c = _conn()
        try:
            g = lambda q, a=(): c.execute(q, a).fetchone()[0] or 0
            return {
                "days": days,
                "answers": g("SELECT COUNT(*) FROM answer_log WHERE ts >= ?", (since,)),
                "low_confidence": g("SELECT COUNT(*) FROM answer_log WHERE ts >= ? AND ok = 0", (since,)),
                "thumbs_up": g("SELECT COUNT(*) FROM answer_log WHERE ts >= ? AND vote = 'up'", (since,)),
                "thumbs_down": g("SELECT COUNT(*) FROM answer_log WHERE ts >= ? AND vote = 'down'", (since,)),
                "open": g("SELECT COUNT(*) FROM answer_log WHERE (ok = 0 OR vote = 'down') AND resolved = 0"),
                "clients": [dict(r) for r in c.execute(
                    "SELECT client, COUNT(*) AS answers, SUM(CASE WHEN ok=0 THEN 1 ELSE 0 END) AS low, "
                    "SUM(CASE WHEN vote='down' THEN 1 ELSE 0 END) AS down FROM answer_log "
                    "WHERE ts >= ? GROUP BY client ORDER BY low DESC, answers DESC LIMIT 20", (since,)).fetchall()],
            }
        finally:
            c.close()


def resolve(answer_id, note=None):
    with _LOCK:
        c = _conn()
        try:
            cur = c.execute("UPDATE answer_log SET resolved=1, resolve_note=?, resolved_ts=? WHERE id=?",
                            (_clean(note, 300) if note else None,
                             datetime.now(timezone.utc).replace(tzinfo=None).isoformat(timespec="seconds"), int(answer_id)))
            c.commit()
            return cur.rowcount == 1
        finally:
            c.close()
