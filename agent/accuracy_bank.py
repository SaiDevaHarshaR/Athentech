"""Self-checking accuracy bank.

For each client: ask the real agent a fixed set of plain questions, run a reference SQL on the same client database,
and compare the number in the answer with the number from the database. Read-only. Results: logs/accuracy_bank.json.
Note: several questions are served by fixed reports, so those checks mainly prove routing, period and rounding are right;
the reference SQL is written here, separately from the report code.
"""
from __future__ import annotations

import json
import os
import re
import threading
from datetime import date, datetime, timedelta, timezone

_LOCK = threading.Lock()
STATE = {"running": False, "done": 0, "total": 0, "client": ""}
_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs", "accuracy_bank.json")

PERIODS = ["today", "yesterday", "this week", "last week", "this month", "last month"]
PER_KIND = 3          # questions per kind per client per run (phrasing and periods are picked at random, so every run asks different things)


def _coll(p):
    from agent.schema_ctx import coll_amt
    return coll_amt(p)


def _pri(p):
    from agent.schema_ctx import pri_amt
    return pri_amt(p, "p")


# kind -> (phrasings, sql builder(profile)->sql with 2 date params, 'num' = one number / 'name' = first row's name)
BANK = [
    ("bills", ["how many bills {p}", "number of bills generated {p}", "bills count {p}", "how many bills were made {p}"],
     lambda p: "SELECT COUNT(DISTINCT BILLNO) FROM trninvlabpri WHERE BILLDATE >= ? AND BILLDATE < ?", "num"),
    ("patients", ["how many patients registered {p}", "new patient registrations {p}", "patients registered {p}"],
     lambda p: "SELECT COUNT(*) FROM mstpatientregistration WHERE %s >= ? AND %s < ?" % (p.get("pat_date", "REGDATE"), p.get("pat_date", "REGDATE")), "num"),
    ("collection", ["total collection {p} across all branches", "what is the overall collection {p}", "how much did we collect {p}", "all branches collection {p}"],
     lambda p: "SELECT SUM(%s) FROM trnmodeofcollectionsdet WHERE DATEOFBILL >= ? AND DATEOFBILL < ?" % _coll(p), "num"),
    ("cash", ["how much cash was collected {p}", "cash collection {p}", "total cash {p}"],
     lambda p: "SELECT SUM(%s) FROM trnmodeofcollectionsdet WHERE UPPER(LTRIM(RTRIM(MODE)))='CASH' AND DATEOFBILL >= ? AND DATEOFBILL < ?" % _coll(p), "num"),
    ("authenticated", ["how many reports were authenticated {p}", "authenticated reports {p}", "number of authenticated reports {p}"],
     lambda p: "SELECT COUNT(*) FROM trninvstatus WHERE STATUS = 'Authenticated' AND AUTHENTICATEDATE >= ? AND AUTHENTICATEDATE < ?", "num"),
    ("concession", ["total concession given {p}", "how much discount was given {p}", "concession total {p}"],
     lambda p: "SELECT SUM(CONCESSIONAMOUNT) FROM trnmodeofcollectionsdet WHERE DATEOFBILL >= ? AND DATEOFBILL < ?", "num"),
    ("refunds", ["how much was refunded {p}", "total refunds {p}", "refund amount {p}"],
     lambda p: "SELECT SUM(%s) FROM trnmodeofcollectionsdet WHERE TYPE = 'LabRefund' AND DATEOFBILL >= ? AND DATEOFBILL < ?" % _coll(p), "num"),
    ("due", ["due payments received {p}", "how much due was collected {p}", "total due payments {p}"],
     lambda p: "SELECT SUM(%s) FROM trnmodeofcollectionsdet WHERE TYPE = 'DUE PAYMENT' AND DATEOFBILL >= ? AND DATEOFBILL < ?" % _coll(p), "num"),
    ("cancelled", ["how many tests were cancelled {p}", "cancelled tests {p}", "number of cancelled tests {p}"],
     lambda p: "SELECT COUNT(*) FROM trninvlabdet WHERE TESTSTATUS = 'Cancelled' AND BILLDATE >= ? AND BILLDATE < ?", "num"),
    ("tests", ["how many tests were done {p}", "total number of tests {p}", "test count {p}"],
     lambda p: "SELECT COUNT(*) FROM trninvlabdet WHERE BILLDATE >= ? AND BILLDATE < ?", "num"),
    ("top_test", ["which test was done the most {p}", "most frequent test {p}", "top test {p}"],
     lambda p: "SELECT TOP 1 i.INVNAME FROM trninvlabdet d JOIN mstInvestigations i ON d.TCODE = i.INVCODE WHERE d.BILLDATE >= ? AND d.BILLDATE < ? GROUP BY i.INVNAME ORDER BY COUNT(*) DESC", "name"),
    ("top_doctor", ["which referring doctor brought the most revenue {p}", "top referring doctor by revenue {p}", "highest revenue referring doctor {p}"],
     lambda p: "SELECT TOP 1 d.DOCNAME FROM trninvlabpri p JOIN mstrefdoctor d ON p.REFDOCTCODE = d.DOCID WHERE p.BILLDATE >= ? AND p.BILLDATE < ? GROUP BY d.DOCNAME ORDER BY SUM(%s) DESC" % _pri(p), "name"),
]


def _dates(period):
    t = date.today()
    if period == "today":
        return t, t + timedelta(days=1)
    if period == "yesterday":
        return t - timedelta(days=1), t
    if period == "this month":
        return t.replace(day=1), t + timedelta(days=1)
    first = t.replace(day=1)
    return (first - timedelta(days=1)).replace(day=1), first


_NUM = re.compile(r"(?<![\w.])(\d[\d,]*(?:\.\d+)?)\s*(cr|crore|l|lakh|lac|k)?\b", re.I)
_MULT = {"cr": 1e7, "crore": 1e7, "l": 1e5, "lakh": 1e5, "lac": 1e5, "k": 1e3}


def _plain(text):
    """Cards arrive as JSON: turn \\u20b9 style escapes back into characters so '\\u20b920,10,846' reads as '20,10,846'."""
    t = text or ""
    try:
        t = re.sub(r"\\u([0-9a-fA-F]{4})", lambda m: chr(int(m.group(1), 16)), t)
    except Exception:
        pass
    return t.replace("\\n", " ")


def _short(text, n=140):
    t = _plain(text)
    t = re.sub(r"```[a-z\-]*", " ", t)
    t = re.sub(r"[{}\[\]\"]", " ", t)
    return re.sub(r"\s+", " ", t).strip()[:n]


def numbers_in(text):
    """[(value, tolerance)] for every figure in an answer (understands 1,23,456 and 1.2L / 3.4Cr / 5K)."""
    text = _plain(text)
    out = []
    for m in _NUM.finditer(text or ""):
        try:
            v = float(m.group(1).replace(",", ""))
        except ValueError:
            continue
        suf = (m.group(2) or "").lower()
        if suf in _MULT:
            v *= _MULT[suf]
            out.append((v, v * 0.006))
        else:
            out.append((v, max(0.5, abs(v) * 0.0005)))
    return out


def matches(ref, answer):
    return any(abs(v - float(ref)) <= max(tol, 0.5) for v, tol in numbers_in(answer))


def _store():
    try:
        with open(_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save(d):
    try:
        os.makedirs(os.path.dirname(_FILE), exist_ok=True)
        with open(_FILE, "w", encoding="utf-8") as f:
            json.dump(d, f)
    except Exception:
        pass


def results():
    d = _store()
    return {"running": dict(STATE), "clients": d}


def _reference(conn, profile, builder, mode, period):
    a, b = _dates(period)
    cur = conn.cursor()
    cur.execute(builder(profile), (a.isoformat(), b.isoformat()))
    r = cur.fetchone()
    if mode == "name":
        return str(r[0]).strip() if r and r[0] is not None else ""
    return float(r[0] or 0) if r else 0.0


def _norm_name(t):
    return re.sub(r"[^a-z0-9]+", " ", _plain(t).lower()).strip()


def run_client(client, ask=None, connect=None, profile_fn=None, periods=None, per_kind=None, rng=None):
    """Returns {'ts','passed','failed','skipped','results':[...]}. `ask(question)->answer text` and `connect()->conn` are injectable."""
    import random
    from agent import heal
    rng = rng or random.Random()
    creds = None
    if ask is None or connect is None:
        creds = heal._client_creds(client)
        if not creds:
            return {"error": "client connection details unavailable"}
    if ask is None:
        from agent import regression
        ask = lambda q: regression._ask(creds, client, q)[0]
    if connect is None:
        from database.connection import get_hospital_connection
        connect = lambda: get_hospital_connection(creds["db_name"], creds["db_server"], creds["db_user"], creds["db_password"])
    if profile_fn is None:
        from agent.schema_ctx import get_profile
        profile_fn = lambda c: get_profile(c, creds["db_name"], creds["db_server"]) if creds else {}
    out = []
    conn = connect()
    if not conn:
        return {"error": "could not connect to the client database"}
    try:
        prof = profile_fn(conn) or {}
        pool = list(periods or PERIODS)
        for kind, phrasings, builder, mode in BANK:
            for per in rng.sample(pool, min(per_kind or PER_KIND, len(pool))):
                q = rng.choice(phrasings).format(p=per)
                row = {"kind": kind, "period": per, "question": q}
                try:
                    ref = _reference(conn, prof, builder, mode, per)
                except Exception as e:
                    row.update(status="skipped", note="reference query not possible on this database: " + type(e).__name__)
                    out.append(row)
                    continue
                row["expected"] = ref
                if ref == 0 or ref == "":
                    row.update(status="skipped", note="no data in this period")
                    out.append(row)
                    continue
                try:
                    ans = ask(q) or ""
                except Exception as e:
                    row.update(status="fail", note="agent error: " + type(e).__name__)
                    out.append(row)
                    continue
                row["answer"] = _short(ans, 300)
                if mode == "name":
                    good = _norm_name(ref) in _norm_name(ans)
                    shown = "%s" % ref
                else:
                    good = matches(ref, ans)
                    shown = "%d" % round(ref) if ref == int(ref) else "%g" % ref
                if good:
                    row["status"] = "pass"
                else:
                    got = [v for v, _ in numbers_in(ans)][:3]
                    row.update(status="fail", note="%s | answer: %s" % (
                        ("database says %s" % shown) if mode == "name" else "answer shows %s, database says %s" % (", ".join("%g" % g for g in got) or "no number", shown),
                        _short(ans, 130)))
                out.append(row)
    finally:
        try:
            conn.close()
        except Exception:
            pass
    p = sum(1 for r in out if r["status"] == "pass")
    f = sum(1 for r in out if r["status"] == "fail")
    s = sum(1 for r in out if r["status"] == "skipped")
    return {"ts": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(timespec="seconds"), "passed": p, "failed": f, "skipped": s,
            "accuracy": round(100.0 * p / (p + f), 1) if (p + f) else None, "results": out}


def _clients():
    try:
        from database.license_db import get_conn
        c = get_conn()
        try:
            return [str(dict(r.items()) .get("client_prefix") if hasattr(r, "items") else r[0]) for r in c.execute(
                "SELECT client_prefix FROM institutions WHERE client_prefix IS NOT NULL AND client_prefix<>''").fetchall()]
        finally:
            c.close()
    except Exception:
        return []


def run_bg(client=None):
    if not _LOCK.acquire(blocking=False):
        return False

    def work():
        try:
            cl = [client] if client else _clients()
            STATE.update(running=True, done=0, total=len(cl))
            for c in cl:
                STATE["client"] = c
                try:
                    res = run_client(c)
                except Exception as e:
                    res = {"error": type(e).__name__}
                d = _store()
                d[c] = res
                _save(d)
                STATE["done"] += 1
        finally:
            STATE.update(running=False, client="")
            _LOCK.release()
    threading.Thread(target=work, daemon=True, name="accuracy-bank").start()
    return True
