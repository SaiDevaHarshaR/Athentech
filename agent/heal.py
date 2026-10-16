"""Self-heal for flagged answers (👎 / low confidence): diagnose -> propose -> test -> HUMAN approves -> revertible.

A fix is only ever a small piece of *guidance text* (plus an optional tested example SELECT) that is added to the
agent's prompt for one client (or, if the admin explicitly chooses, for all clients). It never edits code, never
writes to a client database, and nothing is live until an admin approves it. Every change is audited and can be
reverted in one click; reverting removes the guidance from the prompt immediately.

Storage: logs/heal.db (SQLite). Never raises into the answering path (notes_for is defensive).
"""
from __future__ import annotations

import contextvars
import json
import os
import re
import sqlite3
import threading
from datetime import datetime, timezone

_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
_DB = os.environ.get("SAHASRA_HEAL_DB") or os.path.join(_DIR, "heal.db")
_LOCK = threading.Lock()
PREVIEW = contextvars.ContextVar("heal_preview_rule", default=None)   # lets us test a rule BEFORE approval

MAX_RULE = 400
MAX_INJECT_CHARS = 1400

_SCHEMA = """
CREATE TABLE IF NOT EXISTS heal_proposals(
  id INTEGER PRIMARY KEY AUTOINCREMENT, answer_id INTEGER, client TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',          -- pending | approved | rejected | reverted
  scope TEXT NOT NULL DEFAULT 'client',            -- client | global (admin chooses at approval)
  created_ts TEXT, decided_ts TEXT, decided_by TEXT,
  cause TEXT, diagnosis TEXT, rule_text TEXT, keywords TEXT, example_sql TEXT,
  confidence INTEGER, confidence_why TEXT, risk TEXT,
  before_json TEXT, after_json TEXT, evidence_json TEXT, note TEXT);
CREATE INDEX IF NOT EXISTS ix_hp_client ON heal_proposals(client, status);
CREATE TABLE IF NOT EXISTS heal_events(
  id INTEGER PRIMARY KEY AUTOINCREMENT, pid INTEGER, ts TEXT, actor TEXT, action TEXT, detail TEXT);
"""


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat(timespec="seconds")


def _conn():
    os.makedirs(os.path.dirname(_DB), exist_ok=True)
    c = sqlite3.connect(_DB, timeout=5)
    c.row_factory = sqlite3.Row
    c.executescript(_SCHEMA)
    return c


def _event(c, pid, actor, action, detail=""):
    c.execute("INSERT INTO heal_events(pid,ts,actor,action,detail) VALUES(?,?,?,?,?)",
              (pid, _now(), actor or "system", action, str(detail)[:500]))


# ----------------------------------------------------------------------------- safety helpers
_BAD_SQL = re.compile(r"\b(insert|update|delete|drop|alter|truncate|create|exec|execute|merge|grant|revoke|"
                      r"into|xp_\w+|sp_\w+|openrowset|opendatasource|bulk|shutdown|waitfor)\b", re.I)
_INJECTION = re.compile(r"(ignore (all |any )?(previous|prior|above)|disregard|system prompt|jailbreak|"
                        r"reveal .*(password|secret|key)|you are now)", re.I)


def safe_select(sql: str) -> bool:
    s = (sql or "").strip().rstrip(";").strip()
    if not s or ";" in s or "--" in s or "/*" in s:
        return False
    if not re.match(r"(?is)^(select|with)\b", s):
        return False
    return not _BAD_SQL.search(s)


def clean_rule(text: str) -> str:
    t = re.sub(r"[\x00-\x1f\x7f]+", " ", str(text or "")).strip()
    t = re.sub(r"\s{2,}", " ", t)
    if _INJECTION.search(t):
        return ""
    return t[:MAX_RULE]


def _mask(text, n=600):
    t = str(text or "")
    t = re.sub(r"(?i)(pwd|password|passwd|uid|user id)\s*=\s*[^;\s]+", r"\1=***", t)
    t = re.sub(r"\b\d{10}\b", "**********", t)
    return t[:n]


# ----------------------------------------------------------------------------- reading
def _answer_row(answer_id):
    from agent import answer_log
    with answer_log._LOCK:
        c = answer_log._conn()
        try:
            r = c.execute("SELECT * FROM answer_log WHERE id=?", (int(answer_id),)).fetchone()
            return answer_log._row(r) if r else None
        finally:
            c.close()


def _client_creds(client):
    """Connection details of an institution by its client_prefix (read from the admin DB). None if unknown."""
    try:
        from database.license_db import get_conn
        from auth.secrets_crypto import decrypt_secret
        c = get_conn()
        try:
            r = c.execute("SELECT * FROM institutions WHERE UPPER(client_prefix)=UPPER(?)", (client,)).fetchone()
        finally:
            c.close()
        if not r:
            return None
        d = dict(r.items()) if hasattr(r, "items") else dict(r)
        return {"db_name": d.get("db_name"), "db_server": d.get("db_server"), "db_user": d.get("db_user"),
                "db_password": decrypt_secret(d.get("db_password")), "hospital_name": d.get("name") or client,
                "institution_type": (d.get("type") or "Diagnostic").strip().lower()}
    except Exception:
        return None


def _run_readonly(creds, sql, limit=20):
    """Run ONE validated SELECT on the client's DB. Returns {ok, rows, cols, error}."""
    if not safe_select(sql):
        return {"ok": False, "error": "Not a single safe SELECT; refused."}
    from database.connection import get_hospital_connection
    conn = None
    try:
        conn = get_hospital_connection(creds["db_name"], creds["db_server"], creds["db_user"], creds["db_password"])
        if not conn:
            return {"ok": False, "error": "Could not connect to the client database."}
        cur = conn.cursor()
        cur.execute(sql)
        cols = [d[0] for d in (cur.description or [])]
        rows = [list(map(lambda v: None if v is None else str(v)[:60], r)) for r in cur.fetchmany(limit)]
        return {"ok": True, "cols": cols, "rows": rows, "n": len(rows)}
    except Exception as e:
        from agent.guardian import _clean
        return {"ok": False, "error": _clean(str(e), 300)}
    finally:
        try:
            if conn:
                conn.close()
        except Exception:
            pass


# ----------------------------------------------------------------------------- the diagnosis
_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")


def _table_names(sqls):
    names = []
    for q in sqls or []:
        for m in re.finditer(r"(?i)\b(?:from|join)\s+\[?(?:dbo\.)?\[?([A-Za-z_][A-Za-z0-9_]*)\]?", q or ""):
            t = m.group(1)
            if _IDENT.match(t) and t.lower() not in [n.lower() for n in names]:
                names.append(t)
    return names[:6]


def _columns_text(creds, sqls):
    """Real column names of the tables the flagged SQL used, so the AI never has to guess them."""
    out = []
    if not creds:
        return "not available"
    for t in _table_names(sqls):
        r = _run_readonly(creds, "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = '%s' ORDER BY ORDINAL_POSITION" % t, limit=80)
        if r.get("ok") and r.get("rows"):
            out.append(t + ": " + ", ".join(x[0] for x in r["rows"]))
        elif r.get("ok"):
            out.append(t + ": (table not found)")
    return "\n".join(out)[:1800] or "not available"


_PROMPT = """You are the self-repair assistant for a hospital-data AI agent that answers questions with read-only SQL.
A user's answer was flagged. Work out the most likely cause and propose ONE small fix.

QUESTION: {question}
FLAGGED BECAUSE: {reasons}
USER NOTE: {note}
SQL THE AGENT RAN:
{sql}
RE-RUN OF THAT SQL (read-only): {rerun}
ACTUAL COLUMNS OF THE TABLES USED (taken from the database; use ONLY these names, never invent one):
{columns}
ANSWER PREVIEW: {preview}

Reply with JSON ONLY, no prose:
{{"cause": "one of: wrong_table_or_column | date_handling | wrong_metric | missing_filter | no_data | ungrounded_numbers | unclear_question | other",
  "diagnosis": "1-2 plain sentences an administrator can verify",
  "rule": "ONE short guidance sentence (max 300 chars) telling the agent how to answer this kind of question correctly for this client. Only facts you can see in the evidence. No instructions about ignoring rules.",
  "keywords": ["3-6 lowercase words that identify questions this rule applies to"],
  "example_sql": "OPTIONAL single corrected SELECT, or empty string",
  "confidence": 0-100,
  "confidence_why": "short reason",
  "risk": "low | medium | high - how bad if this guidance is wrong"}}
If the evidence does not show a real defect (e.g. the user just disliked a correct answer), say cause "unclear_question", confidence <= 30 and an empty rule."""


def _extract_json(text):
    t = str(text or "")
    m = re.search(r"\{.*\}", t, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


def _ask_llm(client, prompt):
    from agent.agent import _data_chain
    chain = _data_chain(client, True)
    if not chain:
        raise RuntimeError("No AI provider is available for this client.")
    last = None
    for _name, model in chain:
        try:
            out = model.invoke(prompt)
            return getattr(out, "content", None) or str(out)
        except Exception as e:     # try the next provider of the SAME client chain only
            last = e
    raise last or RuntimeError("AI call failed")


def create_proposal(answer_id, actor="admin", llm=None):
    """Diagnose a flagged answer and store a PENDING proposal. Returns the proposal dict (or {'error':...})."""
    row = _answer_row(answer_id)
    if not row:
        return {"error": "Answer not found."}
    client = row["client"]
    with _LOCK:
        c = _conn()
        try:
            ex = c.execute("SELECT id FROM heal_proposals WHERE answer_id=? AND status='pending' LIMIT 1",
                           (int(answer_id),)).fetchone()
        finally:
            c.close()
    if ex:
        return get_proposal(ex["id"])

    creds = _client_creds(client)
    sqls = [q for q in (row.get("sql_json") or []) if safe_select(q)][:2]
    rerun = "not run (client connection details unavailable)"
    rerun_data = []
    if creds:
        rerun_data = [dict(sql=_mask(q, 300), **_run_readonly(creds, q)) for q in sqls]
        rerun = json.dumps([{k: v for k, v in r.items() if k != "sql"} for r in rerun_data])[:700] if rerun_data else "no SQL was logged"

    prompt = _PROMPT.format(
        question=_mask(row.get("question"), 400), reasons="; ".join(row.get("reasons") or []) or "user gave a thumbs-down",
        note=_mask(row.get("vote_note") or "none", 300), sql="\n".join(_mask(q, 700) for q in sqls) or "none logged",
        columns=_columns_text(creds, sqls), rerun=rerun, preview=_mask(row.get("preview") or "not stored", 400))
    try:
        raw = (llm or _ask_llm)(client, prompt)
    except Exception as e:
        return {"error": "The AI for this client could not be reached, so no fix could be proposed: " + _mask(e, 160)}
    d = _extract_json(raw) or {}

    rule = clean_rule(d.get("rule"))
    example = (d.get("example_sql") or "").strip()
    conf = max(0, min(100, int(d.get("confidence") or 0))) if str(d.get("confidence", "")).strip().lstrip("-").isdigit() else 0
    why = [str(d.get("confidence_why") or "")[:160]]

    # --- test the proposed example on the client's data (read-only) and let the evidence move the confidence
    test = None
    if example:
        if not safe_select(example):
            example, conf = "", min(conf, 40)
            why.append("example SQL rejected by the safety check")
        elif creds:
            test = _run_readonly(creds, example)
            if test.get("ok"):
                conf = min(85, conf + 10) if test["n"] else min(conf, 55)
                why.append("example SQL ran on the client's data" + (f" and returned {test['n']} row(s)" if test["n"] else " but returned no rows"))
            else:
                first_err = str(test.get("error"))[:200]
                fixed = False
                try:   # one self-correction pass using the real error + real columns
                    raw2 = (llm or _ask_llm)(client, prompt + "\n\nYOUR EXAMPLE SQL FAILED:\n" + example +
                                              "\nERROR: " + first_err + "\nFix it using ONLY the actual column names listed above, "
                                              "or return an empty example_sql if unsure. Same JSON format.")
                    d2 = _extract_json(raw2) or {}
                    ex2 = (d2.get("example_sql") or "").strip()
                    if ex2 and safe_select(ex2):
                        t2 = _run_readonly(creds, ex2)
                        if t2.get("ok"):
                            d, example, test, fixed = d2, ex2, t2, True
                            rule = clean_rule(d2.get("rule")) or rule
                            conf = max(0, min(100, int(d2.get("confidence") or 0))) if str(d2.get("confidence", "")).strip().isdigit() else conf
                            conf = min(85, conf + 10) if t2["n"] else min(conf, 55)
                            why.append("first example failed (%s); corrected using the real columns and it ran OK" % first_err[:70])
                except Exception:
                    pass
                if not fixed:
                    example = ""          # never show a query that does not run
                    conf = min(conf, 30)
                    why.append("example SQL failed when tested and could not be corrected: " + first_err[:120])
    conf = min(conf, 85)      # a query that runs proves syntax, not correctness - never show 100%
    if not rule:
        conf = min(conf, 25)
        why.append("no usable guidance was produced")
    if d.get("cause") == "unclear_question":
        conf = min(conf, 30)

    before = {"question": _mask(row.get("question"), 400), "answer_preview": _mask(row.get("preview"), 500),
              "score": row.get("score"), "reasons": row.get("reasons"), "sql": [_mask(q, 700) for q in (row.get("sql_json") or [])],
              "vote": row.get("vote"), "vote_note": _mask(row.get("vote_note"), 300), "rerun_of_logged_sql": rerun_data}
    after = {"example_sql_test": test}

    # --- re-ask the question with the proposed rule applied (preview only, not live) so the admin sees before/after
    if rule and creds:
        try:
            from agent.agent import ask_agent
            tok = PREVIEW.set(rule)
            try:
                ans, _ = ask_agent(row.get("question") or "", creds["db_name"], [], True, row.get("role") or "viewer",
                                   creds["hospital_name"], creds["db_server"], creds["db_user"], creds["db_password"],
                                   client, creds["institution_type"])
            finally:
                PREVIEW.reset(tok)
            after["answer_preview"] = _mask(ans, 900)
        except Exception as e:
            after["answer_error"] = _mask(e, 200)
            why.append("could not re-ask the question to preview the result")

    with _LOCK:
        c = _conn()
        try:
            cur = c.execute(
                "INSERT INTO heal_proposals(answer_id,client,status,scope,created_ts,cause,diagnosis,rule_text,keywords,"
                "example_sql,confidence,confidence_why,risk,before_json,after_json,evidence_json) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (int(answer_id), client, "pending", "client", _now(), str(d.get("cause") or "other")[:40],
                 _mask(d.get("diagnosis"), 400), rule, json.dumps([str(k).lower()[:24] for k in (d.get("keywords") or [])][:6]),
                 example[:1500], conf, "; ".join(w for w in why if w)[:400],
                 str(d.get("risk") or "medium")[:10], json.dumps(before), json.dumps(after), "{}"))
            pid = cur.lastrowid
            _event(c, pid, actor, "proposed", f"answer {answer_id}, confidence {conf}")
            c.commit()
        finally:
            c.close()
    return get_proposal(pid)


# ----------------------------------------------------------------------------- reading / deciding
def _prow(r):
    d = dict(r)
    for k in ("keywords", "before_json", "after_json", "evidence_json"):
        try:
            d[k] = json.loads(d.get(k) or "null")
        except Exception:
            d[k] = None
    return d


def get_proposal(pid):
    with _LOCK:
        c = _conn()
        try:
            r = c.execute("SELECT * FROM heal_proposals WHERE id=?", (int(pid),)).fetchone()
            if not r:
                return None
            d = _prow(r)
            d["events"] = [dict(e) for e in c.execute("SELECT ts,actor,action,detail FROM heal_events WHERE pid=? ORDER BY id", (int(pid),))]
            return d
        finally:
            c.close()


def list_proposals(status=None, limit=100):
    with _LOCK:
        c = _conn()
        try:
            q = "SELECT * FROM heal_proposals" + (" WHERE status=?" if status else "") + " ORDER BY id DESC LIMIT ?"
            args = ([status] if status else []) + [max(1, min(int(limit), 300))]
            out = []
            for r in c.execute(q, args):
                d = _prow(r)
                for k in ("before_json", "after_json", "evidence_json"):
                    d.pop(k, None)
                out.append(d)
            return out
        finally:
            c.close()


def decide(pid, action, actor="admin", scope=None, note=None, rule_text=None):
    """action: approve | reject | revert. Returns the updated proposal or {'error':...}."""
    with _LOCK:
        c = _conn()
        try:
            r = c.execute("SELECT * FROM heal_proposals WHERE id=?", (int(pid),)).fetchone()
            if not r:
                return {"error": "Proposal not found."}
            st = r["status"]
            if action == "approve":
                if st != "pending":
                    return {"error": f"Only a pending proposal can be approved (this one is {st})."}
                rule = clean_rule(rule_text) if rule_text is not None else r["rule_text"]
                if not rule:
                    return {"error": "There is no usable guidance text to approve."}
                sc = "global" if scope == "global" else "client"
                c.execute("UPDATE heal_proposals SET status='approved',scope=?,rule_text=?,decided_ts=?,decided_by=?,note=? WHERE id=?",
                          (sc, rule, _now(), actor, (note or "")[:300], int(pid)))
                _event(c, pid, actor, "approved", f"scope={sc}" + (" (rule edited)" if rule_text is not None and rule != r["rule_text"] else ""))
            elif action == "reject":
                if st != "pending":
                    return {"error": f"Only a pending proposal can be rejected (this one is {st})."}
                c.execute("UPDATE heal_proposals SET status='rejected',decided_ts=?,decided_by=?,note=? WHERE id=?",
                          (_now(), actor, (note or "")[:300], int(pid)))
                _event(c, pid, actor, "rejected", note or "")
            elif action == "revert":
                if st != "approved":
                    return {"error": "Only an approved fix can be reverted."}
                c.execute("UPDATE heal_proposals SET status='reverted',decided_ts=?,decided_by=?,note=? WHERE id=?",
                          (_now(), actor, (note or "")[:300], int(pid)))
                _event(c, pid, actor, "reverted", note or "")
            else:
                return {"error": "Unknown action."}
            c.commit()
        finally:
            c.close()
    return get_proposal(pid)


# ----------------------------------------------------------------------------- used by the agent prompt
def notes_for(client, question=""):
    """Approved guidance for this client (+ global), most relevant first. '' when none. Never raises."""
    try:
        rules = []
        pv = PREVIEW.get()
        if pv:
            rules.append(pv)
        if client:
            q = (question or "").lower()
            with _LOCK:
                c = _conn()
                try:
                    rows = c.execute("SELECT rule_text,keywords,scope FROM heal_proposals WHERE status='approved' "
                                     "AND (scope='global' OR UPPER(client)=UPPER(?)) ORDER BY id DESC LIMIT 30",
                                     (str(client),)).fetchall()
                finally:
                    c.close()
            scored = []
            for r in rows:
                try:
                    kws = json.loads(r["keywords"] or "[]")
                except Exception:
                    kws = []
                hit = sum(1 for k in kws if k and k in q)
                if kws and not hit:
                    continue
                scored.append((hit, r["rule_text"]))
            rules += [t for _, t in sorted(scored, key=lambda x: -x[0])]
        out, used = [], 0
        for t in rules:
            if t and used + len(t) <= MAX_INJECT_CHARS:
                out.append("- " + t)
                used += len(t)
        if not out:
            return ""
        return ("\n### Administrator-approved guidance for this institution (cannot override read-only or security rules)\n"
                + "\n".join(out) + "\n")
    except Exception:
        return ""
