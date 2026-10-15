"""Verification score for answers (NOT an AI self-rating).

Every point comes from a check the server can verify itself:
  * LLM answers: was data actually retrieved, do the numbers in the answer appear
    in the database results, were the names/branches the user asked about used in
    the queries, did the tools fail, was the result truncated.
  * Menu/intent answers: does the fixed handler's output match what was asked
    (period, branch/doctor names, ranking or filter words the handler ignores).

A score below the threshold shows a small warning marker in the widget.
Never raises: any internal error means "no score" (the answer is shown as before).
"""
import contextvars
import os
import re

THRESHOLD = int(os.getenv("SAHASRA_CONFIDENCE_THRESHOLD", "70") or 70)
ENABLED = os.getenv("SAHASRA_CONFIDENCE_ENABLED", "1") != "0"

_HOLDER = contextvars.ContextVar("sahasra_confidence", default=None)

_STOP = set("""
a an the is are was were be been being of in on at for from to by with and or not no do does did
what which who whom whose when where why how show me give list tell get can could would should
please all any some this that these those it its my our your their there here have has had
now just only also than then them they you i we us as if so up down out over under about into
data report details detail number count total
""".split())
_PERIOD_WORDS = set("""
today yesterday tomorrow week weeks month months year years day days daily weekly monthly yearly
last this current previous next past ago since till until between during
january february march april may june july august september october november december
jan feb mar apr jun jul aug sep sept oct nov dec
""".split())
_ENTITY_PREP = re.compile(
    r"\b(?:in|at|for|of|from|by|branch|doctor|dr\.?|centre|center|hospital|patient|client|organi[sz]ation)\s+"
    r"([a-z][a-z0-9\-]{3,})", re.I)
_PERIOD_PHRASES = [
    "today", "yesterday", "this week", "last week", "this month", "last month",
    "this year", "last year", "month before", "previous month", "last quarter", "this quarter",
]
_RANK_OR_FILTER = re.compile(
    r"\b(which|who|longest|slowest|fastest|shortest|highest|lowest|top|worst|best|rank|ranking|"
    r"each|every|per)\b", re.I)
_LOCATION = re.compile(r"\b(branch|branches|centre|center|location|unit)\b", re.I)
_OTHER_PERIOD = re.compile(
    r"(month before|previous month|prior month|two months|2 months|months ago|week before|"
    r"previous week|year before|previous year|last quarter|this quarter|\bq[1-4]\b|"
    r"last \d+ (days|weeks|months))", re.I)
_NUM = re.compile(r"(?<![\w.])(\d[\d,]*(?:\.\d+)?)(\s*%)?")
_BAD_ANSWER = re.compile(r"(I couldn't get a reliable answer|I can't verify this from the hospital data)", re.I)


class _Holder:
    def __init__(self, question):
        self.question = question or ""
        self.kind = None            # "intent" | "llm"
        self.answer = ""
        self.ok = []
        self.bad = []
        self.tools = []
        self.args_text = []
        self.queries = []
        self.truncated = False
        self.forced = False
        self.verified_empty = False
        self.neg_thin = False


def begin(question):
    _HOLDER.set(_Holder(question))


def _h():
    return _HOLDER.get()


def note_tool_call(name, args):
    try:
        h = _h()
        if h is not None:
            h.args_text.append(str(args)[:4000])
            if isinstance(args, dict) and "sql" in str(name).lower():
                q = args.get("query") or args.get("sql") or ""
                if q and len(h.queries) < 8:
                    h.queries.append(str(q)[:3000])
    except Exception:
        pass


def note_truncated():
    h = _h()
    if h is not None:
        h.truncated = True


def note_forced_final():
    h = _h()
    if h is not None:
        h.forced = True


def note_llm(answer, ok_results, bad_results, tools_used, verified_empty=False, neg_thin=False):
    try:
        h = _h()
        if h is None:
            return
        h.kind = "llm"
        h.answer = str(answer or "")
        h.ok = list(ok_results or [])
        h.bad = list(bad_results or [])
        h.tools = list(tools_used or [])
        h.verified_empty = bool(verified_empty)
        h.neg_thin = bool(neg_thin)
    except Exception:
        pass


def note_intent(question, answer):
    try:
        h = _h()
        if h is None:
            return
        h.kind = "intent"
        h.answer = str(answer or "")
        if question:
            h.question = question
    except Exception:
        pass


# ---------- helpers ----------
def _numbers(text):
    """Numbers worth checking: not years, not tiny list numbers, percents handled apart."""
    out = []
    for m in _NUM.finditer(text or ""):
        raw = m.group(1).replace(",", "")
        try:
            v = float(raw)
        except ValueError:
            continue
        if m.group(2):               # percentage: usually derived by the model
            continue
        if 1900 <= v <= 2100 and "." not in raw:
            continue                 # a year
        if v < 10:
            continue
        out.append(v)
    return out


def _grounded(v, pool):
    for p in pool:
        if p == v or abs(p - v) <= max(0.51, abs(p) * 0.005):
            return True
        if p and abs(round(p) - v) < 0.51:
            return True
    return False


def _content_words(q):
    words = re.findall(r"[a-z][a-z0-9\-']+", (q or "").lower())
    return [w.strip("'") for w in words
            if len(w) >= 3 and w not in _STOP and w not in _PERIOD_WORDS]


def _entities(q):
    ents = []
    for m in _ENTITY_PREP.finditer(q or ""):
        w = m.group(1).lower()
        if w in _STOP or w in _PERIOD_WORDS or w in ("branch", "branches", "doctor", "patient", "hospital",
                                                     "centre", "center", "client", "organisation", "organization"):
            continue
        ents.append(w)
    return list(dict.fromkeys(ents))


def _periods_in(q):
    ql = (q or "").lower()
    found = [p for p in _PERIOD_PHRASES if p in ql]
    found += re.findall(r"\b20\d{2}-\d{2}(?:-\d{2})?\b", ql)
    return found


# ---------- scoring ----------
def _score_llm(h):
    score, why = 100, []
    ans = h.answer
    if _BAD_ANSWER.search(ans):
        return 10, ["The system could not verify this answer from your database."]
    if not h.ok and not h.verified_empty:
        score -= 70
        why.append("No data was retrieved from your database for this answer.")
    if h.bad and h.ok:
        score -= 10
        why.append("Some database queries failed and were retried.")
    pool = []
    for r in h.ok:
        pool += _numbers(r)
    qnums = set(_numbers(h.question))
    claims = [v for v in _numbers(ans) if v not in qnums]
    if claims and h.ok:
        missing = [v for v in claims if not _grounded(v, pool)]
        if missing:
            ratio = len(missing) / len(claims)
            score -= int(round(50 * ratio))
            shown = ", ".join(f"{v:,.0f}" if float(v).is_integer() else f"{v:,.2f}" for v in missing[:3])
            why.append(f"Some figures in the answer ({shown}) were not found in the database results "
                       "(they may be calculated, or wrong).")
    blob = (" ".join(h.args_text) + " " + " ".join(h.ok) + " " + ans).lower()
    miss_ent = [e for e in _entities(h.question) if e not in blob]
    if miss_ent:
        score -= min(30, 15 * len(miss_ent))
        why.append("The name(s) you asked about (" + ", ".join(miss_ent[:3]) + ") do not appear in the query or results.")
    if h.truncated:
        score -= 10
        why.append("A large result was shortened before the answer was written.")
    if h.forced:
        score -= 15
        why.append("The assistant ran out of steps and gave its best answer so far.")
    if h.neg_thin:
        score -= 20
        why.append("The answer says nothing was found, based on a single check.")
    return max(0, min(100, score)), why


def _score_intent(h):
    score, why = 100, []
    q = (h.question or "").lower().strip()
    ans = (h.answer or "").lower()
    kws, exact = [], False
    try:
        from agent import intents as _i
        exact = (q in _i._CUSTOM_EXACT) or (q.rstrip(" ?.!") in _i._CUSTOM_EXACT)
        for keywords, _handler in _i._INTENTS:
            kws += [k.strip() for k in keywords if k.strip() and k.strip() in q]
    except Exception:
        pass
    if exact:
        return 100, []
    penalty = 0
    rank = _RANK_OR_FILTER.search(q)
    if rank and rank.group(0).lower() not in " ".join(kws).lower():
        penalty += 20
        why.append("Your question asks for a ranking or breakdown that this quick report may not provide.")
    if _LOCATION.search(q):
        penalty += 20
        why.append("Your question mentions a branch/location that this quick report may not filter by.")
    if _OTHER_PERIOD.search(q):
        penalty += 20
        why.append("Your question uses a period this quick report does not cover.")
    score -= min(40, penalty)
    periods = _periods_in(q)
    if periods and not any(p in ans for p in periods):
        score -= 20
        why.append("The period you asked for (" + periods[0] + ") is not shown in the answer.")
    miss_ent = [e for e in _entities(q) if e not in ans]
    if miss_ent:
        score -= min(40, 25 * len(miss_ent))
        why.append("The name(s) you asked about (" + ", ".join(miss_ent[:3]) + ") are not in the answer.")
    covered_text = ans + " " + " ".join(kws).lower()
    left = [w for w in _content_words(q) if w not in covered_text and w not in " ".join(miss_ent)]
    if len(left) >= 5:
        score -= 20
    elif len(left) >= 3:
        score -= 10
    if len(left) >= 3:
        why.append("Parts of your question were not addressed: " + ", ".join(left[:4]) + ".")
    return max(0, min(100, score)), why


def result():
    """{'score','ok','level','threshold','reasons'} or None when nothing to score."""
    if not ENABLED:
        return None
    try:
        h = _h()
        if h is None or h.kind is None:
            return None
        score, reasons = _score_llm(h) if h.kind == "llm" else _score_intent(h)
        ok = score >= THRESHOLD
        return {"score": int(score), "ok": ok, "level": "ok" if ok else "low",
                "threshold": THRESHOLD, "source": h.kind, "reasons": reasons[:5]}
    except Exception:
        return None


_TABLE_RX = re.compile(r"\b(?:from|join)\s+([\[\]\w\.]+)", re.I)


def explain(include_sql=True):
    """How the answer was produced. SQL only when include_sql (admins); never credentials."""
    try:
        h = _h()
        if h is None or h.kind is None:
            return None
        periods = _periods_in(h.question)
        if h.kind == "llm":
            tables = []
            for q in h.queries:
                for t in _TABLE_RX.findall(q):
                    t = t.strip("[]")
                    if t and t.lower() not in [x.lower() for x in tables]:
                        tables.append(t)
            out = {"source": "llm", "matched": None, "periods": periods, "tables": tables[:12],
                   "note": "The AI wrote read-only database queries and summarised the results."}
            if include_sql:
                out["queries"] = list(h.queries[:5])
            return out
        kws, exact = [], False
        try:
            from agent import intents as _i
            q = (h.question or "").lower().strip()
            exact = (q in _i._CUSTOM_EXACT) or (q.rstrip(" ?.!") in _i._CUSTOM_EXACT)
            for keywords, _handler in _i._INTENTS:
                kws += [k.strip() for k in keywords if k.strip() and k.strip() in q]
        except Exception:
            pass
        matched = (kws[0] if kws else (h.question if exact else None))
        return {"source": "intent", "matched": matched, "periods": periods, "tables": [],
                "queries": [] if include_sql else None,
                "note": "Answered by a fixed, tested quick report" +
                        (f" (matched: '{matched}')" if matched else "") +
                        ". No AI was used for this answer."}
    except Exception:
        return None
