"""
Contextual follow-up suggestions shown as tap-chips under an answer. Zero tokens: rule based, and every
suggestion is a phrase that one of our instant intents answers (verified by tests against the real intent
lists), so tapping a chip is fast and free.
"""
import json
import re

_CARD = re.compile(r"```(?:dashboard|list|search)-card\s*(\{.*?\})\s*```", re.S)
_REFUSAL = re.compile(r"\b(error|could not|couldn't|cannot|can't|unable|not available|no llm|expired|invalid)\b")

_LIS = [
    (r"refund", ["List refunds", "Total collection", "Outstanding due"]),
    (r"\b(due|outstanding|credit|unpaid)\b", ["Credit bills", "Total collection", "Collection by branch"]),
    (r"\btat\b|turnaround|overdue", ["Pending tests", "Stuck samples", "Lab dashboard"]),
    (r"pending|stuck|awaiting|sample|authenticat", ["TAT compliance", "Stuck samples", "Authenticated today"]),
    (r"package", ["Top packages", "List packages", "Top tests"]),
    (r"referr|doctor", ["Top referring doctors", "Top tests", "Total collection"]),
    (r"patient|uhid|registration", ["Recent patients", "Registrations today", "Total collection"]),
    (r"test|investigation|cbp|hba1c|volume|\bmri\b|ct scan|ultrasound|x-ray|xray", ["Top tests", "Top packages", "Pending tests"]),
    (r"collection|revenue|earning|paid|cash|upi|payment", ["Collection by branch", "Collection by payment mode", "Collection growth"]),
    (r"branch|location", ["Collection by branch", "Top tests", "Total collection"]),
    (r"dashboard|department|\blab\b|radiology", ["TAT compliance", "Pending tests", "Top tests"]),
]
_LIS_DEFAULT = ["Today's collection data", "Top tests", "Pending tests"]

_HIS = [
    (r"pharmacy|stock|medicine", ["Low stock", "Pharmacy purchases", "Pharmacy returns"]),
    (r"\bbeds?\b|ward|room|occupan|admitted|admission", ["Bed occupancy", "Currently admitted", "Ward census"]),
    (r"appointment", ["Today's appointments", "Doctor wise revenue", "Day collection"]),
    (r"expens|voucher|expenditure", ["Expenses today", "Day collection", "Total hospital revenue"]),
    (r"\bop\b|outpatient|opd", ["IP revenue", "Doctor wise revenue", "Day collection"]),
    (r"\bip\b|inpatient", ["OP revenue", "Compare OP and IP revenue", "Bed occupancy"]),
    (r"doctor", ["Doctor wise revenue", "Today's appointments", "Day collection"]),
    (r"revenue|collection|income", ["OP revenue", "IP revenue", "Compare OP and IP revenue"]),
    (r"patient|uhid", ["Currently admitted", "Today's appointments", "Day collection"]),
    (r"test|investigation", ["Investigations today", "Test catalog", "Day collection"]),
]
_HIS_DEFAULT = ["Day collection", "Bed occupancy", "Today's appointments"]


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", "", (s or "").lower().replace("'", "")).strip()


def _card_title(answer: str) -> str:
    m = _CARD.search(answer or "")
    if not m:
        return ""
    try:
        return str(json.loads(m.group(1)).get("title", ""))
    except Exception:
        t = re.search(r'"title"\s*:\s*"([^"]+)"', m.group(1))
        return t.group(1) if t else ""


def suggest_followups(question: str, answer: str, institution_type: str = "diagnostic", limit: int = 3) -> list:
    """Up to `limit` short follow-up questions, never repeating what was just asked. [] for errors/refusals."""
    answer = answer or ""
    if not answer.strip() or (not _CARD.search(answer) and _REFUSAL.search(answer[:140].lower())):
        return []
    rules, default = (_HIS, _HIS_DEFAULT) if institution_type == "hospital" else (_LIS, _LIS_DEFAULT)
    topic = f"{question or ''} {_card_title(answer)}".lower()
    pool = []
    for pattern, suggestions in rules:
        if re.search(pattern, topic):
            pool += suggestions
            if len(pool) >= limit * 2:
                break
    pool += default
    asked, out, seen = _norm(question), [], set()
    for s in pool:
        n = _norm(s)
        if n in seen or (asked and (n in asked or asked in n)):
            continue
        seen.add(n); out.append(s)
        if len(out) == limit:
            break
    return out
