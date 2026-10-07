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
    "collection": ["Collection by branch this month", "Collection by payment mode this month", "Collection growth", "Total collection yesterday",
                   "Total collection this month", "Top branches by collection this month", "Total concession this month", "Total collection this week", "Total collection last month", "UPI total this month"],
    "payment":    ["Total UPI this month", "Total cash collected this month", "Collection by payment mode this month", "Collection by branch this month", "Total cheque this month", "Total credit card this month", "UPI total this month", "Total collection this week"],
    "refund":     ["List refunds this month", "Total refunds this month", "Total collection this month", "Outstanding due this month", "Cancelled tests this month", "Refunds today", "Recent refunds this month"],
    "due":        ["Credit bills", "Outstanding due this month", "Total collection this month", "Collection by branch this month", "How many bills today", "Previous due this month", "Unpaid bills", "Zero paid bills"],
    "tat":        ["TAT compliance", "Overdue TAT", "Average TAT", "Pending tests today", "Stuck samples", "Lab dashboard", "Tests exceeding TAT", "TAT alert"],
    "labops":     ["Pending tests today", "Stuck samples", "Authenticated today", "Samples collected today", "Status breakdown today", "TAT compliance", "Lab dashboard", "Sample rejected this month", "Rejection count this month", "Acknowledged count today", "Result entry count today", "How many tests done today", "Authenticated count today"],
    "package":    ["Top packages this month", "List packages", "Top tests this month", "Total collection this month", "Package orders this month", "Health packages", "Available packages"],
    "doctor":     ["Top referring doctors this month", "Area wise business", "Business by marketing executive", "Top tests this month", "Total collection this month", "Top doctors this month", "Who referred most this month", "Top 10 referring doctors this month", "Which areas"],
    "patient":    ["Recent patients", "Registrations today", "How many patients today", "Total collection this month", "Top tests this month", "Latest patients", "Last 10 patients", "New patients today", "Latest registrations today"],
    "test":       ["Top tests this month", "Most ordered tests this month", "CBP volume this month", "RBS volume this month", "MRI count this month", "Ultrasound procedures this month", "Top packages this month", "Cancelled tests this month", "Top investigations this month", "X-ray count this month", "CT scan count this month", "Mammography volume this month", "CUE volume this month", "CBP count this month", "Cancellation count this month"],
    "branch":     ["Collection by branch this month", "List all branches", "Top branches by collection this month", "Top tests this month", "Total collection yesterday", "Active branches", "How many branches"],
    "dashboard":  ["Lab dashboard", "Radiology dashboard", "TAT compliance", "Pending tests today", "List departments", "Haematology dashboard", "Biochemistry dashboard", "Microbiology dashboard", "Which departments"],
    "general":    ["Today's collection data", "Top tests this month", "Pending tests today", "Recent patients", "TAT compliance", "Top referring doctors this month", "Top doctors this month", "Credit bills", "Total refunds this month", "Collection by branch this month"],
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
    "revenue":      ["OP revenue this month", "IP revenue this month", "Compare OP and IP revenue", "Total hospital revenue this month", "Doctor wise revenue this month", "Collection yesterday", "Collection this month", "Day collection today", "Overall revenue this month", "Combined revenue this month", "Collection this year", "OP collection this month", "IP collection this month", "Outpatient revenue this month", "Inpatient revenue this month"],
    "op":           ["IP revenue this month", "Doctor wise revenue this month", "Today's appointments", "Collection this month", "Day collection today"],
    "ip":           ["OP revenue this month", "Compare OP and IP revenue", "Bed occupancy", "Currently admitted", "Total hospital revenue this month"],
    "beds":         ["Bed occupancy", "Beds available", "Ward census", "Room census", "Currently admitted", "Occupied beds", "How many beds", "Bed status", "Rooms by floor", "Ward occupancy"],
    "appointments": ["Today's appointments", "Doctor appointments today", "Doctor wise revenue this month", "Day collection today", "Beds available", "Appointment list today"],
    "pharmacy":     ["Low stock", "Reorder level", "Pharmacy purchases this month", "Pharmacy returns this month", "Pharmacy issues this month", "Goods received this month", "Stock report", "Pharmacy GRN this month", "Sales returns this month", "Department issues this month"],
    "expense":      ["Expenses today", "Expenses yesterday", "Vouchers this month", "Day collection today", "Total hospital revenue this month", "Expenses this month"],
    "doctor":       ["Doctor wise revenue this month", "Today's appointments", "Doctor appointments today", "Day collection today", "OP revenue this month"],
    "patient":      ["Currently admitted", "Today's appointments", "Beds available", "Day collection today", "Admitted patients", "Who is admitted"],
    "test":         ["Investigations today", "Investigations this month", "Test catalog", "Day collection today", "Lab tests today", "Tests ordered this month", "List investigations"],
    "equipment":    ["Equipment usage this month", "Day collection today", "Total hospital revenue this month", "Medical equipment this month"],
    "general":      ["Day collection today", "Bed occupancy", "Today's appointments", "OP revenue this month", "Low stock", "Expenses today", "Currently admitted", "Total hospital revenue this month", "Pharmacy purchases this month"],
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


_UNFILTERED = object()


def all_chips(institution_type: str = "diagnostic") -> list:
    """Every chip we might ever show for this kind of institution (used by chip_health to test them)."""
    pools = _HIS_POOLS if institution_type == "hospital" else _LIS_POOLS
    out = []
    for pool in pools.values():
        for s in pool:
            if s not in out:
                out.append(s)
    return out


def suggest_followups(question: str, answer: str, institution_type: str = "diagnostic", limit: int = 3, verified=_UNFILTERED) -> list:
    """Up to `limit` short follow-up questions, never repeating what was just asked. [] for errors/refusals."""
    answer = answer or ""
    if verified is None:                       # chip health check for this institution is still running
        return []
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
        if verified is not _UNFILTERED and s not in verified:
            return False
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