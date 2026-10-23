"""Fast, strict report router (no LLM). Maps a plainly worded count/total/ranking question to
run_report() arguments. run_report builds SQL from each client's own schema profile, so this
works for any lab. READ-ONLY. If ANY word is unknown, or run_report cannot do it, returns None
and the normal AI path answers."""
import re

_FILLER = set("""a an the of in for on at to by me my our us we is are was were be been do does did what whats which who
how many much total number count show give tell list display get see please can you i it this that these those and or
with from all any overall full amount amounts value""".split())
_PERIODS = [
    (r"last (\d{1,3}) days?", lambda m: f"last_{m.group(1)}_days"),
    (r"(?:past|previous) (\d{1,3}) days?", lambda m: f"last_{m.group(1)}_days"),
    (r"today", lambda m: "today"), (r"yesterday", lambda m: "yesterday"),
    (r"this week|current week", lambda m: "this_week"), (r"last week|previous week", lambda m: "last_week"),
    (r"this month|current month", lambda m: "this_month"), (r"last month|previous month", lambda m: "last_month"),
    (r"this year|current year", lambda m: "this_year"), (r"last year|previous year", lambda m: "last_year"),
]
_MODS = [(r"ct scans?|ct", "CT"), (r"mri scans?|mri", "MRI"), (r"x[- ]?rays?", "X-Ray"),
         (r"ultrasounds?|usg|sonography", "Ultrasound"), (r"mammography|mammogram", "Mammography"),
         (r"dopplers?", "Doppler"), (r"2d echo|echo", "Echo")]
_GROUPS = [(r"(?:per|by|each|every) day|daily|day[- ]?wise|day by day", "day"),
           (r"(?:per|by|each|every) month|monthly|month[- ]?wise", "month"),
           (r"(?:per|by|each|every) branch|branch[- ]?wise|by location|per location|location[- ]?wise", "branch"),
           (r"(?:per|by|each|every) doctor|doctor[- ]?wise|by referring doctors?", "doctor"),
           (r"(?:per|by|each|every) department|department[- ]?wise", "department"),
           (r"(?:per|by|each|every) (?:payment )?mode|mode[- ]?wise", "mode")]
_METRICS = [(r"sample rejections?|rejected samples?", ("tests", "Sample Rejected")),
            (r"average bill value|average bill amount|average bill|avg bill value|avg bill|average invoice value", ("avg_bill", None)),
            (r"total billed value|billed value|bill value|billing value|total billing", ("bill_value", None)),
            (r"refunds?", ("refunds", None)),
            (r"collections?|revenue|income|earnings?", ("revenue", None)),
            (r"new patients?|patients? registered|patient registrations?|registrations?|patients", ("patients", None)),
            (r"bills|invoices|billing", ("bills", None)),
            (r"tests|investigations|orders|scans|procedures", ("tests", None))]


def _cut(q, rx):
    m = re.search(r"\b(?:" + rx + r")\b", q)
    return (m, q[:m.start()] + " " + q[m.end():]) if m else (None, q)


def parse(question):
    q = re.sub(r"[?!.,]", " ", (question or "").lower())
    q = re.sub(r"\s+", " ", q).strip()
    if not q or len(q) > 120:
        return None
    period = None
    for rx, fn in _PERIODS:
        m, q2 = _cut(q, rx)
        if m:
            period, q = fn(m), q2
            break
    group = "none"
    m, q2 = _cut(q, r"which branch (?:collected|has|had|made|earned|got|is) the (?:most|highest|maximum|top|best)(?: collection| revenue| money)?")
    if m and period and not q2.split() == [] and all(w in _FILLER for w in q2.split()):
        return dict(metric="revenue", group_by="branch", period=period, modality=None, status=None)
    if m and period and not q2.split():
        return dict(metric="revenue", group_by="branch", period=period, modality=None, status=None)
    for rx, g in _GROUPS:
        m, q2 = _cut(q, rx)
        if m:
            group, q = g, q2
            break
    modality = None
    for rx, name in _MODS:
        m, q2 = _cut(q, rx)
        if m:
            modality, q = name, q2
            break
    metric = status = None
    for rx, (mt, st) in _METRICS:
        m, q2 = _cut(q, rx)
        if m:
            metric, status, q = mt, st, q2
            break
    if modality and metric in (None, "tests"):
        metric = "tests"
    if not metric or not period:
        return None
    left = [w for w in q.split() if w not in _FILLER]
    if left:                       # ANY unknown word -> AI path
        return None
    if modality and metric != "tests":
        return None
    if metric == "revenue" and group in ("doctor", "department"):
        return None
    return dict(metric=metric, group_by=group, period=period,
                modality=modality, status=status)


def try_fast_report(question, role, db_name, db_server=None, db_user=None, db_password=None):
    args = parse(question)
    if not args:
        return None
    try:
        from agent.report_tool import run_report
        out = run_report.invoke({**{k: v for k, v in args.items() if v}, "top_n": 15, "role": role,
                                 "db_name": db_name, "db_server": db_server,
                                 "db_user": db_user, "db_password": db_password})
    except Exception:
        return None
    if not isinstance(out, str):
        return None
    if out.startswith(("Unsupported", "Error", "Query failed")):
        return None
    if out.startswith("No rows:") and args["metric"] != "refunds":
        return None          # an empty result might be a wrong column guess: let the careful AI path check it
    if out.startswith("No rows:"):
        return out.split("Sources checked:")[0].replace("No rows:", "No records found:").strip() + \
            " (checked the lab's own records for that period)."
    return out
