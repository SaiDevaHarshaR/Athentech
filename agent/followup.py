"""Chat polish helpers (pure functions, no I/O): follow-up rewriting, contextual chips, friendly errors, plain-language 'how calculated'.
Everything fails soft: on any doubt the original text is returned unchanged."""
import re
import uuid

_PERIODS = ["last 30 days", "last 7 days", "month to date", "today", "yesterday", "this week", "last week", "this month",
            "last month", "this year", "last year", "this quarter", "last quarter"]
_PER_RX = re.compile(r"\b(" + "|".join(re.escape(p) for p in _PERIODS) + r")\b", re.I)
_CONNECT = re.compile(r"^\s*(and|also|then|now|ok|okay|so)\b[,\s]*", re.I)
_LEAD = re.compile(r"^\s*(what about|how about|and for|same for|same but for|same thing for|now for|only for|just for|for|in|only|just)\b[\s,:]*", re.I)
_BRANCH_WORDS = re.compile(r"[?.!]+$")


def _user_msgs(history):
    out = []
    for m in history or []:
        role = m.get("role") if isinstance(m, dict) else getattr(m, "role", "")
        txt = m.get("content") if isinstance(m, dict) else getattr(m, "content", "")
        if role == "user" and txt:
            out.append(str(txt))
    return out


def rewrite(question, history):
    """'and last month?' + previous 'collection this week'  ->  'collection last month'. None = leave as is."""
    try:
        q = (question or "").strip()
        users = _user_msgs(history)
        # history may already contain the current question as its last user message
        if users and users[-1].strip() == q:
            users = users[:-1]
        if not q or not users:
            return None
        prev = users[-1].strip()
        if len(prev) < 4 or len(q.split()) > 8:
            return None
        body = _BRANCH_WORDS.sub("", q).strip()
        had_lead = bool(_CONNECT.match(body) or _LEAD.match(body))
        core = _LEAD.sub("", _CONNECT.sub("", body)).strip()
        low = core.lower()
        pm = _PER_RX.findall(core)
        # A) only a new period (optionally with a connector): swap / add the period of the previous question
        if pm and _PER_RX.sub("", core).strip(" ,.-") == "" and (had_lead or len(core.split()) <= 3):
            newp = pm[0].lower()
            if _PER_RX.search(prev):
                return _PER_RX.sub(newp, prev, count=1)
            return prev.rstrip("?. ") + " " + newp
        # B) 'same for <something>' / 'what about <something>' : narrow the previous question
        if had_lead and core and not pm and len(core.split()) <= 4 and not re.search(r"\b(how|what|why|show|list|give|which|who)\b", low):
            return prev.rstrip("?. ") + " for " + core
        # C) period + entity in one go: 'and for jagtial last month'
        if had_lead and pm and len(core.split()) <= 6:
            ent = _PER_RX.sub("", core).strip(" ,.-")
            base = _PER_RX.sub(pm[0].lower(), prev, count=1) if _PER_RX.search(prev) else prev.rstrip("?. ") + " " + pm[0].lower()
            return base.rstrip("?. ") + (" for " + ent if ent else "")
        return None
    except Exception:
        return None


_SWAP = {"today": "yesterday", "yesterday": "today", "this week": "last week", "last week": "this week", "this month": "last month",
         "last month": "this month", "this year": "last year", "last year": "this year"}


def contextual(question):
    """0-2 chips derived from the question just answered (same wording, other period) - these reuse a question shape that worked."""
    try:
        q = (question or "").strip().rstrip("?. ")
        m = _PER_RX.search(q)
        out = []
        if m and m.group(1).lower() in _SWAP and len(q) < 70:
            out.append(_PER_RX.sub(_SWAP[m.group(1).lower()], q, count=1))
        return out[:2]
    except Exception:
        return []


_ERR_RULES = [
    (r"timeout|timed out|HYT00", "The hospital database took too long to respond. Please try again in a minute."),
    (r"pyodbc|login failed|08001|server was not found|cannot open database|connection (refused|reset)|database .*unavailable|could not connect",
     "I can't reach this hospital's database right now. Please try again shortly - if it keeps happening, contact AthenTech support."),
    (r"rate.?limit|429|quota|too many requests|busy", "The AI service is busy right now. Please try again in a moment."),
    (r"traceback|exception|internal server error|\b500\b|sqlstate|syntax error|invalid column|invalid object", "Something went wrong on our side while looking that up. Please try again, or rephrase the question."),
]


def friendly_error(raw):
    """-> (message, ref). The raw text must be logged by the caller under `ref`; the person only sees the message."""
    ref = uuid.uuid4().hex[:6].upper()
    t = str(raw or "")
    for rx, msg in _ERR_RULES:
        if re.search(rx, t, re.I):
            return msg + " (ref %s)" % ref, ref
    return "Something went wrong while answering. Please try again. (ref %s)" % ref, ref


_TECH_ANSWER = re.compile(r"traceback|pyodbc|sqlstate|\[Microsoft\]\[ODBC|invalid column name|invalid object name|syntax error near|ODBC Driver", re.I)


def looks_technical(answer):
    return bool(_TECH_ANSWER.search(answer or ""))


_TBL = re.compile(r"\b(?:trn|mst|his|tbl|vw)[A-Z][A-Za-z0-9_]{3,}\b")


def sanitize_answer(text):
    """Never show raw table names in a chat answer. Leaves cards/code blocks alone."""
    if not text or "```" in text:
        return text
    return _TBL.sub("the records", text)


def plain_explain(ex, confidence_ok=True):
    """Plain wording for the 'How was this calculated?' dialog: no table names, no SQL."""
    ex = dict(ex or {})
    src = ex.get("source")
    for k in ("tables", "queries", "matched"):
        ex.pop(k, None)
    if src == "intent":
        ex["note"] = "Answered by a fixed, tested report built into Sahasra - no AI estimate is involved."
    else:
        ex["note"] = ("The AI looked this up in your hospital data and summarised it. Every figure was checked against what the database returned."
                      if confidence_ok else
                      "The AI looked this up in your hospital data and summarised it. Some figures could not be fully confirmed - please verify them in Sahasra.")
    ex["plain"] = True
    return ex


_REF = re.compile(r"\b(it|its|they|them|their|that|those|these|this one|he|she|him|her|there|same|above|previous|earlier|before|again|instead|"
                  r"also|too|more|rest|other|others|else|compare|vs|versus|why|how come)\b|^\s*(and|but|so|then|ok|okay|what about|how about)\b", re.I)


def is_standalone(question):
    """True when the question can be answered with no earlier chat (so old turns would only add noise and cost time)."""
    try:
        q = (question or "").strip()
        return len(q.split()) >= 4 and not _REF.search(q)
    except Exception:
        return False


def period_mismatch(question, answer):
    """Period asked (e.g. 'yesterday') is absent from the answer while a different period is named -> note text, else ''."""
    try:
        asked = {m.lower() for m in _PER_RX.findall(question or "")}
        if len(asked) != 1:
            return ""
        got = {m.lower() for m in _PER_RX.findall(answer or "")}
        if got and not (asked & got):
            return ("Check the period: you asked for %s, but this answer mentions %s." % (next(iter(asked)), ", ".join(sorted(got))))
        return ""
    except Exception:
        return ""
