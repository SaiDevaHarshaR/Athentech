"""Plain-language safety verdict for a Heal proposal, so a non-technical admin can decide without reading SQL.
Pure function of the stored proposal (no database / AI calls). level: ok | warn | block.
'block' = approving is refused by the server (SAHASRA_HEAL_ENFORCE=0 turns the refusal off)."""
from __future__ import annotations


def _fmt(v):
    try:
        return f"{float(v):,.0f}" if float(v).is_integer() else f"{float(v):,.2f}"
    except Exception:
        return str(v)


def verdict(p: dict) -> dict:
    p = p or {}
    a = p.get("after_json") or {}
    b = p.get("before_json") or {}
    checks = []          # (status, text)  status: ok | warn | block

    def add(st, text):
        checks.append({"status": st, "text": text})

    if (p.get("rule_text") or "").strip():
        add("ok", "A guidance rule was written.")
    else:
        add("block", "No usable guidance rule was produced - there is nothing to approve.")

    t = a.get("example_sql_test")
    if t is None:
        add("warn", "No test query was run, so the fix could not be checked against the database.")
    elif not t.get("ok"):
        add("block", "The test query failed on the client's database (%s). Do not approve." % str(t.get("error") or "error")[:100])
    elif not t.get("n"):
        add("warn", "The test query ran but returned no rows - the data it relies on may not exist for this client.")
    else:
        add("ok", "The test query ran on the client's database and returned %d row(s) (shown below as proof)." % t["n"])

    if a.get("answer_error") or not (a.get("answer_preview") or "").strip():
        add("block", "The question could not be re-asked with the fix, so the 'After' answer is unknown. Do not approve.")
    else:
        un = a.get("unverified") or []
        if un:
            add("block", "The 'After' answer contains numbers that are NOT in the database results (%s) - they may be invented."
                % ", ".join(_fmt(v) for v in un[:4]))
        elif "unverified" in a:
            add("ok", "Every number in the 'After' answer was found in the database results.")
        else:
            add("warn", "This proposal pre-dates number checking: compare the 'After' numbers with the proof table yourself.")

    conf = p.get("confidence")
    if isinstance(conf, (int, float)):
        if conf >= 70:
            add("ok", "The AI is fairly confident in this fix (%d%%)." % conf)
        elif conf >= 50:
            add("warn", "Medium AI confidence (%d%%) - read the Before and After answers carefully." % conf)
        else:
            add("warn", "Low AI confidence (%d%%)." % conf)
    if p.get("scope") == "global":
        add("warn", "Scope is ALL clients - only choose this if every hospital has the same problem.")

    level = "block" if any(c["status"] == "block" for c in checks) else ("warn" if any(c["status"] == "warn" for c in checks) else "ok")
    head = {"ok": "Looks safe to approve", "warn": "Check these points before approving", "block": "Not safe to approve"}[level]
    proof = None
    if t and t.get("ok") and t.get("rows"):
        proof = {"title": "What the database actually returned for the test query", "cols": t.get("cols") or [], "rows": t["rows"][:10]}
    elif b.get("rerun_of_logged_sql"):
        r = [x for x in b["rerun_of_logged_sql"] if x.get("ok") and x.get("rows")]
        if r:
            proof = {"title": "What the database returned for the original query", "cols": r[0].get("cols") or [], "rows": r[0]["rows"][:10]}
    return {"level": level, "headline": head, "checks": checks, "proof": proof}
