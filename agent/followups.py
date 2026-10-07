"""
Contextual follow-up suggestions shown as tap-chips under an answer. Zero tokens: rule based, and every
suggestion is a phrase one of our instant intents answers (verified by tests against the real intent
lists), so tapping a chip is fast and free.

Each topic has a pool of ~6-8 chips. We show 2 on-topic ones (rotating, so repeated questions do not always
show the same chips) + 1 from a neighbouring topic to encourage exploring. Never repeats what was just asked.
"""
import json
import re
import zlib

_CARD = re.compile(r"```(?:dashboard|list|search)-card\s*(\{.*?\})\s*```", re.S)
_REFUSAL = re.compile(r"\b(error|could not|couldn't|cannot|can't|unable|not available|no llm|expired|invalid)\b")

# ------------------------------------------------------------------ diagnostics / LIS
_LIS_POOLS = {
    "collection": ["Collection by branch", "Collection by payment mode", "Collection growth", "Total collection yesterday",
                   "Total collection this month", "Top branches by collection", "Cash in hand", "Total concession this month"],
    "payment":    ["Total UPI this month", "Total cash collected", "Collection by payment mode", "Cash in hand", "Collection by branch"],
    "refund":     ["List refunds", "Total refunds this month", "Total collection this month", "Outstanding due", "Cancelled tests"],
    "due":        ["Credit bills", "Outstanding due", "Total collection this month", "Collection by branch", "How many bills today"],
    "tat":        ["TAT compliance", "Overdue TAT", "Average TAT", "Pending tests", "Stuck samples", "Lab dashboard"],
    "labops":     ["Pending tests", "Stuck samples", "Authenticated today", "Samples collected today", "Status breakdown", "TAT compliance", "Lab dashboard"],
    "package":    ["Top packages", "List packages", "Top tests this month", "Total collection this month"],
    "doctor":     ["Top referring doctors", "Area wise business", "Business by marketing executive", "Top tests this month", "Total collection this month"],
    "patient":    ["Recent patients", "Registrations today", "How many patients today", "Total collection this month", "Top tests this month"],
    "test":       ["Top tests this month", "Most ordered tests", "CBP volume", "RBS volume", "MRI count", "Ultrasound procedures", "Top packages", "Cancelled tests"],
    "branch":     ["Collection by branch", "List all branches", "Top branches by collection", "Top tests this month", "Total collection yesterday"],
    "dashboard":  ["Lab dashboard", "Radiology dashboard", "TAT compliance", "Pending tests", "List departments"],
    "general":    ["Today's collection data", "Top tests this month", "Pending tests", "Recent patients", "TAT compliance", "Top referring doctors"],
}
_LIS_RULES = [
    (r"refund", "refund"),
    (r"\b(due|outstanding|credit|unpaid)\b", "due"),
    (r"\btat\b|turnaround|overdue", "tat"),
    (r"pending|stuck|awaiting|sample|authenticat|status", "labops"),
    (r"package", "package"),
    (r"referr|doctor|executive|area", "doctor"),
    (r"patient|uhid|registration", "patient"),
    (r"\bupi\b|\bcash\b|card|cheque|payment mode", "payment"),
    (r"test|investigation|cbp|hba1c|volume|\bmri\b|ct scan|ultrasound|x-ray|xray", "test"),
    (r"collection|revenue|earning|paid|concession|growth", "collection"),
    (r"branch|location", "branch"),
    (r"dashboard|department|\blab\b|radiology", "dashboard"),
]

# ------------------------------------------------------------------ hospitals / HIS
_HIS_POOLS = {
    "revenue":      ["OP revenue", "IP revenue", "Compare OP and IP revenue", "Total hospital revenue", "Doctor wise revenue", "Collection yesterday", "Collection this month", "Day collection"],
    "op":           ["IP revenue", "Doctor wise revenue", "Today's appointments", "Collection this month", "Day collection"],
    "ip":           ["OP revenue", "Compare OP and IP revenue", "Bed occupancy", "Currently admitted", "Total hospital revenue"],
    "beds":         ["Bed occupancy", "Beds available", "Ward census", "Room census", "Currently admitted"],
    "appointments": ["Today's appointments", "Doctor appointments", "Doctor wise revenue", "Day collection", "Beds available"],
    "pharmacy":     ["Low stock", "Reorder level", "Pharmacy purchases", "Pharmacy returns", "Pharmacy issues", "Goods received"],
    "expense":      ["Expenses today", "Expenses yesterday", "Vouchers", "Day collection", "Total hospital revenue"],
    "doctor":       ["Doctor wise revenue", "Today's appointments", "Doctor appointments", "Day collection", "OP revenue"],
    "patient":      ["Currently admitted", "Today's appointments", "Beds available", "Day collection"],
    "test":         ["Investigations today", "Investigations this month", "Test catalog", "Day collection"],
    "equipment":    ["Equipment usage", "Day collection", "Total hospital revenue"],
    "general":      ["Day collection", "Bed occupancy", "Today's appointments", "OP revenue", "Low stock", "Expenses today"],
}
_HIS_RULES = [
    (r"pharmacy|stock|medicine|reorder|grn|goods", "pharmacy"),
    (r"\bbeds?\b|ward|room|occupan|admitted|admission", "beds"),
    (r"appointment", "appointments"),
    (r"expens|voucher|expenditure", "expense"),
    (r"equipment", "equipment"),
    (r"\bop\b|outpatient|opd", "op"),
    (r"\bip\b|inpatient", "ip"),
    (r"doctor|consultation", "doctor"),
    (r"revenue|collection|income", "revenue"),
    (r"patient|uhid", "patient"),
    (r"test|investigation", "test"),
]

# kept for tests / backwards compatibility
_LIS_DEFAULT, _HIS_DEFAULT = _LIS_POOLS["general"][:3], _HIS_POOLS["general"][:3]
_LIS = [(p, _LIS_POOLS[k]) for p, k in _LIS_RULES]
_HIS = [(p, _HIS_POOLS[k]) for p, k in _HIS_RULES]


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


def _rotate(items: list, k: int) -> list:
    return items[k % len(items):] + items[:k % len(items)] if items else []


def suggest_followups(question: str, answer: str, institution_type: str = "diagnostic", limit: int = 3) -> list:
    """Up to `limit` short follow-up questions, never repeating what was just asked. [] for errors/refusals."""
    answer = answer or ""
    if not answer.strip() or (not _CARD.search(answer) and _REFUSAL.search(answer[:140].lower())):
        return []
    pools, rules = (_HIS_POOLS, _HIS_RULES) if institution_type == "hospital" else (_LIS_POOLS, _LIS_RULES)
    topic = f"{question or ''} {_card_title(answer)}".lower()
    keys = []
    for pattern, key in rules:
        if re.search(pattern, topic) and key not in keys:
            keys.append(key)
    primary = keys[0] if keys else "general"
    secondary = [k for k in keys[1:]] + ["general"]
    asked, seed = _norm(question), zlib.crc32(_norm(question).encode())

    def ok(s, taken):
        n = _norm(s)
        return n not in taken and not (asked and (n in asked or asked in n))

    out, taken = [], set()
    on_topic = max(1, limit - 1)
    for s in _rotate(pools[primary], seed):                       # 2 on-topic, rotating
        if ok(s, taken) and len(out) < on_topic:
            out.append(s); taken.add(_norm(s))
    for key in secondary:                                         # + 1 from a neighbouring topic
        for s in _rotate(pools[key], zlib.crc32((asked + '|' + primary + '|' + key).encode())):
            if ok(s, taken) and len(out) < limit:
                out.append(s); taken.add(_norm(s))
        if len(out) >= limit:
            break
    return out[:limit]