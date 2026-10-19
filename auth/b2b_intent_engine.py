"""Stage 7B: offline, multilingual, *deterministic* B2B request parser.

No LLM calls, network traffic, SQL generation or client-data access. This is a
request parser only. Authentication and organization scoping stay in b2b_portal.
"""
from __future__ import annotations
from dataclasses import dataclass
import re
import unicodedata

@dataclass(frozen=True)
class Decision:
    intent: str
    period: str | None = None
    status_filter: str | None = None
    reference: str | None = None
    note: str = ""

_PERIODS = {
    "today": ("today", "ఈరోజు", "ఈ రోజు", "आज", "आज का"),
    "yesterday": ("yesterday", "నిన్న", "कल", "बीते दिन"),
    "last_7_days": ("last 7 days", "last seven days", "past week", "గత 7 రోజులు", "पिछले 7 दिन"),
    "this_month": ("this month", "current month", "ఈ నెల", "इस महीने"),
    "last_month": ("last month", "previous month", "గత నెల", "पिछले महीने"),
}
_REF = re.compile(r"\b(?:INV|BILL)[A-Z0-9_-]{2,40}\b", re.IGNORECASE)


def normalize(text: str) -> str:
    if not isinstance(text, str) or len(text) > 700:
        raise ValueError("Question must be text of 700 characters or less")
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", text).casefold()).strip()


def parse_question(text: str) -> Decision:
    q = normalize(text)
    if not q:
        return Decision("help")
    # Never interpret a request for another institution as a broader DB query.
    if any(s in q for s in ("other company", "another company", "all organizations", "all organisations", "other patients", "వేరే సంస్థ", "दूसरी कंपनी")):
        return Decision("forbidden")
    period = next((period for period, phrases in _PERIODS.items() if any(phrase in q for phrase in phrases)), None)
    ym = re.search(r"\b20\d{2}-(?:0[1-9]|1[0-2])(?:-(?:0[1-9]|[12]\d|3[01]))?\b", q)
    if ym: period = ym.group()
    # A report PDF is sensitive. Never auto-serve from a free-form prompt.
    if any(s in q for s in ("pdf", "patient report", "lab report", "test report", "రిపోర్ట్ డౌన్‌లోడ్", "रिपोर्ट डाउनलोड")):
        ref = _REF.search(q)
        return Decision("patient_report", period=period, reference=ref.group().upper() if ref else None,
                        note="Patient reports require separate approved-document entitlement checks.")
    if any(s in q for s in ("excel", "spreadsheet", "xlsx", "export", "ఎక్సెల్", "एक्सेल")):
        return Decision("excel", period=period)
    pending = any(s in q for s in ("pending", "not completed", "awaiting", "పెండింగ్", "పూర్తికాని", "लंबित", "बाकी"))
    completed = any(s in q for s in ("completed", "complete invoices", "finished", "పూర్తయిన", "पूरा हुए", "पूर्ण"))
    if pending and completed:
        return Decision("clarify", period=period, note="Choose pending or completed, not both.")
    stat = "pending" if pending else "completed" if completed else None
    want_list = any(s in q for s in ("show", "list", "which", "details", "status", "statuses", "చూపు", "జాబితా", "दिखा", "सूची", "स्थिति"))
    invoice = any(s in q for s in ("invoice", "invoices", "bill", "bills", "బిల్లు", "బిల్లులు", "बिल", "बिलों"))
    count = any(s in q for s in ("how many", "count", "number of", "ఎన్ని", "कितने", "संख्या"))
    if stat and not invoice:
        return Decision("unsupported_clinical_status", period=period, status_filter=stat,
                        note="Clinical pending/completed status needs per-LIS approved mappings.")
    if stat and invoice:
        return Decision("invoice_status", period=period, status_filter=stat)
    if invoice and (want_list or not count and not any(s in q for s in ("total amount", "billed amount"))):
        return Decision("bills", period=period)
    if any(s in q for s in ("how many", "total", "overview", "summary", "amount", "dashboard", "revenue", "billing", "collection", "ఎన్ని", "మొత్తం", "कितने", "कुल", "सारांश")):
        return Decision("overview", period=period)
    return Decision("help", period=period)
