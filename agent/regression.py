"""Regression suite - every approved Heal fix becomes a saved test question.

Why: a prompt rule that fixes one client's question can quietly change another answer. After any update (or on demand,
or nightly) the saved questions are asked again through the real agent and each must still:
  * return an answer (not an error / "couldn't verify" message)
  * pass the server-side verification (score >= threshold, every figure traceable to the database results)
Stored next to the Heal proposals (logs/heal.db). Read-only against client data (the normal agent path).
CLI:  python -m agent.regression [CLIENT]      -> exit code 1 when any case fails (usable in a deploy script)
"""
from __future__ import annotations

import json
import sys
import threading
from datetime import datetime, timezone

from agent import heal

_SCHEMA = """
CREATE TABLE IF NOT EXISTS regression_cases(
  id INTEGER PRIMARY KEY AUTOINCREMENT, client TEXT NOT NULL, question TEXT NOT NULL, pid INTEGER,
  enabled INTEGER NOT NULL DEFAULT 1, created_ts TEXT, last_run_ts TEXT, last_ok INTEGER, last_note TEXT, last_score INTEGER,
  UNIQUE(client, question));
"""
_RUN_LOCK = threading.Lock()
_BAD = ("couldn't get a reliable answer", "can't verify this from the hospital data", "could not be reached",
        "is not configured for this institution", "rejected the saved api key", "no credits")


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat(timespec="seconds")


def _conn():
    c = heal._conn()
    c.executescript(_SCHEMA)
    return c


def add_case(client, question, pid=None):
    """Called when a Heal fix is approved. Idempotent."""
    q = (question or "").strip()
    if not client or not q:
        return False
    with heal._LOCK:
        c = _conn()
        try:
            c.execute("INSERT OR IGNORE INTO regression_cases(client,question,pid,created_ts) VALUES(?,?,?,?)",
                      (str(client), q[:400], pid, _now()))
            c.execute("UPDATE regression_cases SET enabled=1 WHERE client=? AND question=?", (str(client), q[:400]))
            c.commit()
        finally:
            c.close()
    return True


def list_cases(client=None):
    with heal._LOCK:
        c = _conn()
        try:
            if client:
                rows = c.execute("SELECT * FROM regression_cases WHERE UPPER(client)=UPPER(?) ORDER BY id DESC", (client,)).fetchall()
            else:
                rows = c.execute("SELECT * FROM regression_cases ORDER BY id DESC LIMIT 300").fetchall()
        finally:
            c.close()
    return [dict(r) for r in rows]


def set_enabled(case_id, enabled):
    with heal._LOCK:
        c = _conn()
        try:
            c.execute("UPDATE regression_cases SET enabled=? WHERE id=?", (1 if enabled else 0, int(case_id)))
            c.commit()
        finally:
            c.close()


def delete_case(case_id):
    with heal._LOCK:
        c = _conn()
        try:
            c.execute("DELETE FROM regression_cases WHERE id=?", (int(case_id),))
            c.commit()
        finally:
            c.close()


def _ask(creds, client, question, role="admin"):
    from agent.agent import ask_agent
    from agent import confidence as conf, answer_guard as ag
    conf.begin(question)

    def once(q):
        return ask_agent(q, creds["db_name"], [], True, role, creds["hospital_name"], creds["db_server"],
                         creds["db_user"], creds["db_password"], client, creds["institution_type"])
    ans, tok = once(question)
    ans, tok, info = ag.guard_numbers(once, question, ans, tok, conf)
    return ans, conf.result(), info


def run_case(case):
    """Returns (ok, note, score)."""
    creds = heal._client_creds(case["client"])
    if not creds:
        return False, "client connection details unavailable", None
    try:
        ans, res, info = _ask(creds, case["client"], case["question"])
    except Exception as e:
        return False, "error: " + heal._mask(e, 160), None
    low = (ans or "").lower()
    if not (ans or "").strip():
        return False, "empty answer", None
    if any(b in low for b in _BAD):
        return False, "answer was an error / could-not-verify message", None
    score = (res or {}).get("score")
    if info.get("unverified"):
        return False, "figures not found in database results: " + ", ".join(f"{v:,.0f}" for v in info["unverified"][:3]), score
    if res and not res.get("ok"):
        return False, "verification score %s below threshold (%s)" % (score, "; ".join(res.get("reasons") or [])[:140]), score
    return True, "passed", score


def run_all(client=None, limit=25):
    """Runs enabled cases one after another (one run at a time). Returns {'ran','passed','failed','results':[...]}."""
    if not _RUN_LOCK.acquire(blocking=False):
        return {"error": "A regression run is already in progress."}
    try:
        cases = [c for c in list_cases(client) if c["enabled"]][:limit]
        out = []
        for c in cases:
            ok, note, score = run_case(c)
            with heal._LOCK:
                cx = _conn()
                try:
                    cx.execute("UPDATE regression_cases SET last_run_ts=?,last_ok=?,last_note=?,last_score=? WHERE id=?",
                               (_now(), 1 if ok else 0, note[:300], score, c["id"]))
                    cx.commit()
                finally:
                    cx.close()
            out.append({"id": c["id"], "client": c["client"], "question": c["question"], "ok": ok, "note": note, "score": score})
        failed = [r for r in out if not r["ok"]]
        try:
            from observability import ops_lite
            ops_lite.record_event("regression", "failure" if failed else "success")
        except Exception:
            pass
        return {"ran": len(out), "passed": len(out) - len(failed), "failed": len(failed), "results": out}
    finally:
        _RUN_LOCK.release()


if __name__ == "__main__":
    r = run_all(sys.argv[1] if len(sys.argv) > 1 else None)
    print(json.dumps(r, indent=1)[:4000])
    sys.exit(1 if r.get("failed") or r.get("error") else 0)
