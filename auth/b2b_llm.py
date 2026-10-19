"""B2B assistant LLM fallback. Used only AFTER the fixed org-scoped lookups did not match.
The model gets NO tools and NO database access: it sees a small snapshot of the verified organisation's own figures
(built by the same fixed queries), the client's public knowledge text and website text. It cannot see other organisations."""
import time
from typing import Optional

_SNAP = {}          # (institution_id, org) -> (time, text)
_SNAP_TTL = 120
_PORTAL_HELP = (
    "HOW THIS CHAT / PORTAL WORKS: Corporate users sign in with a one-time code sent to their REGISTERED mobile number (no password exists). "
    "A number that is not registered cannot log in: the lab's team must register it. Extra authorised users, a new mobile number, account activation, "
    "order cancellation or modification, adding a test to an order, bulk patient upload, scanned TRF submission, urgent/priority processing, home collection, "
    "appointments, special rates, report corrections and API / LIS-integration / HIS-sync problems are handled by the lab's staff: tell the user the request "
    "needs staff and that they can raise it right here by typing it (for example 'raise a technical support request', 'sample pickup request', "
    "'report correction request', 'special rate request') so a ticket number is issued. You can show: tests, prices on their rate list, packages, "
    "report and sample status by bill number, pending/delayed tests, rejections, balances, credit limit, invoices, payments, trends and MIS Excel. "
    "This chat cannot show live pickup-executive location, patient UHID lookups or patient personal details; do not pretend it can. "
    "Test method, collection tube, sample volume, stability, storage and run frequency are only known if they appear in KNOWLEDGE; otherwise say the lab will confirm.")
_PROBES = ("what is our outstanding balance and credit limit", "status of my reports this month",
           "tests done this month", "contract agreement details", "which health packages are available")


def _snapshot(inst, contact):
    key = (inst.get("id"), str(contact.get("organisation_code")))
    hit = _SNAP.get(key)
    if hit and time.time() - hit[0] < _SNAP_TTL:
        return hit[1]
    from auth import b2b_assist as A
    from auth.b2b_portal import _lis, _org_name

    def Q(sql, params=()):
        conn = _lis(inst)
        try:
            return conn.execute(sql, params).fetchall()
        finally:
            try: conn.close()
            except Exception: pass
    try:
        name = _org_name(inst, contact.get("organisation_code"))
    except Exception:
        name = None
    parts = []
    for pr in _PROBES:
        try:
            r = A.route(Q, inst, contact, name, pr, "this_month", ticket_ok=False)
        except Exception:
            r = None
        if r and r.get("answer"):
            t = str(r["answer"])
            tb = r.get("table")
            if tb and tb.get("rows"):
                t += " | " + "; ".join(" / ".join(str(c) for c in row) for row in tb["rows"][:12])
            parts.append(t[:700])
    text = ("Organisation: %s (code %s)\n" % (name or "-", contact.get("organisation_code"))) + "\n".join("- " + p for p in parts)
    _SNAP[key] = (time.time(), text[:3200])
    return _SNAP[key][1]


def answer(inst, contact, message, history=None) -> Optional[dict]:
    from agent.guard_strict import screen_input
    ok, msg = screen_input(message, public=True)
    if not ok:
        return {"status": "success", "intent": "guard", "answer": msg}
    from auth.whitelabel import get_config
    cfg = get_config(int(inst["id"]))
    brand = cfg.get("brand_name") or inst.get("name") or "the lab"
    facts = _snapshot(inst, contact)
    know = (cfg.get("b2c_knowledge") or "") + "\n" + (cfg.get("b2b_notice") or "")
    try:
        from auth.site_info import context_for
        know += "\nFROM THE WEBSITE:\n" + context_for(cfg.get("site_url") or "", message)
    except Exception:
        pass
    system = (
        "You are the 24/7 corporate support assistant of %s, talking to a VERIFIED contact of one client organisation.\n"
        "Answer ONLY from the FACTS and KNOWLEDGE below. Never invent prices, times, numbers, dates or policies. "
        "If the answer is not there, say so briefly and offer to raise a support ticket (the user can type e.g. 'raise a complaint', "
        "'sample pickup request', 'talk to the lab manager'). Never discuss other organisations or individual patients. "
        "No medical advice. Be concise (under 120 words), plain text, Indian Rupee amounts as INR.\n\n"
        "FACTS ABOUT THIS ORGANISATION (live from the lab system):\n%s\n\n%s\n\nKNOWLEDGE:\n%s" % (brand, facts, _PORTAL_HELP, know[:5000]))
    from agent.agent import _data_chain, _invoke_with_retry
    chain = _data_chain(str(inst.get("client_prefix") or "").upper(), True, message)
    if not chain:
        return None
    name, llm = chain[0]
    try:
        llm = llm.bind(max_tokens=450)
    except Exception:
        pass
    from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
    msgs = [SystemMessage(content=system)]
    for h in (history or [])[-6:]:
        try:
            c = str(h.get("content", ""))[:500]
            msgs.append((HumanMessage if h.get("role") == "user" else AIMessage)(content=c))
        except Exception:
            pass
    msgs.append(HumanMessage(content=message))
    resp = _invoke_with_retry(llm, msgs, retries=0, current_provider=name)
    text = (resp.content if hasattr(resp, "content") else str(resp or "")).strip() if resp else ""
    if not text:
        return None
    return {"status": "success", "intent": "ai_support", "answer": text}
