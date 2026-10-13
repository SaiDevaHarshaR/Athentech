"""Cash/day-collection reconciliation through SELECT-only calculations.

The original dbo.LabDayCollection_All procedure is NOT called here: it writes
trnTempDayCollAll. Read-only calculations live in day_collection_readonly.py.
The public functions and formatting API remain compatible with the existing
intent handlers and Excel exports. Verify amounts against a saved original LIS
report using tools/verify_recon_parity.py (no procedure execution).
"""

import re
from datetime import datetime, timedelta

from database.connection import get_hospital_connection

# Original trnTempDayCollAll column order, from supplied source procedure.
# Used for strict financial parity comparison, excluding metadata.
_COLUMNS = [
    "USERID", "LOCATION", "BILLDATE", "GTOTALCREDITS", "TOTALCASH", "TOTALCREDITS",
    "TOTALDUES", "TOTALCONCESSIONS", "TOTALCREDITCARDS", "TOTALCHEQUE", "TOTALUPI",
    "TOTALREFUND", "TOTALREFUNDSPREV", "EXPENDITURE", "PREVDUE_CASH", "PREVDUE_CREDITS",
    "PREVDUE_CHEQUE", "PREVDUE_DD", "PREVDUE_UPI", "TOTALONLINEUPI", "TOTALCOREBUSINESSCASH",
    "TOTALCASHRECEIVED", "TOTALCCRECEIVED", "TOTALCHQONLINEUPI", "COMPADVCASH", "COMPADVCC",
    "COMPADVUPI", "COMPADVCHQ", "COMPADVRTGS", "COMPADVAPP", "TOTALCASHINHAND",
    "TOTALCCINHAND", "TOTALCHQINHAND", "TOTALONLINEUPIINHAND", "LOCATIONID",
    "CREATEDATE", "TOTALBILLS",
]

# Maps the real column name to the exact label shown on the printed
# report PDF, so the agent's answer matches what staff already expect.
_REPORT_LABELS = {
    "GTOTALCREDITS": "Grand Total With Credits [GT]",
    "TOTALCASH": "Total Cash [a]",
    "TOTALCREDITS": "Total Credits [b]",
    "TOTALDUES": "(-)Dues [c]",
    "TOTALCONCESSIONS": "(-)Concessions [d]",
    "TOTALCREDITCARDS": "(-)Credit Card Total [e]",
    "TOTALONLINEUPI": "(-)Cheque/DD/UPI Total [f]",
    "TOTALREFUND": "(-)Todays Refund Total [g]",
    "TOTALREFUNDSPREV": "(-)Previous Refunds Total [h]",
    "EXPENDITURE": "(-)Expenditure Total [i]",
    "TOTALCOREBUSINESSCASH": "Core Business Cash Collected [j]",
    "PREVDUE_UPI": "Previous Dues Collected (UPI)",
    "TOTALCASHRECEIVED": "Total Cash Received [o]",
    "TOTALCCRECEIVED": "Total Credit Card Received",
    "TOTALCHQONLINEUPI": "Total Cheque/Online/UPI Received",
    "TOTALCASHINHAND": "Total Cash in Hand [z]",
    "TOTALCCINHAND": "Total Credit Card in Hand",
    "TOTALCHQINHAND": "Total Cheque in Hand",
    "TOTALONLINEUPIINHAND": "Total Online/UPI in Hand",
    "TOTALBILLS": "Total Bills",
}


def _resolve_relative_date(value: str) -> str:
    v = (value or "").strip().lower()
    today = datetime.now().date()
    if v == "today":
        return today.isoformat()
    if v == "yesterday":
        return (today - timedelta(days=1)).isoformat()
    return value


def get_day_collection_all_branches(
    bill_date: str,
    db_name: str,
    db_server=None, db_user=None, db_password=None,
) -> dict:
    """Pure-SELECT reconciliation (reports/day_collection_readonly.py). The service NEVER executes dbo.LabDayCollection_All:
    that procedure DELETEs+INSERTs into trnTempDayCollAll in the client's database. There is deliberately no switch to
    re-enable it. Parity against the real procedure is checked by tools/verify_recon_parity.py (manual, rolled back)."""
    from reports.day_collection_readonly import get_day_collection_all_branches_readonly
    return get_day_collection_all_branches_readonly(bill_date, db_name, db_server, db_user, db_password)


def get_day_collection_one_branch(
    location_keyword: str,
    bill_date: str,
    db_name: str,
    db_server=None, db_user=None, db_password=None,
) -> dict:
    """
    Same real data, filtered to ONE location by name (partial match,
    case-insensitive) — reuses get_day_collection_all_branches so the
    formula logic lives in exactly one place.
    """
    result = get_day_collection_all_branches(bill_date, db_name, db_server, db_user, db_password)
    if "error" in result:
        return result

    kw = (location_keyword or "").strip().lower()
    matches = [b for b in result["branches"] if kw in (b.get("LOCATION") or "").lower()]

    if not matches:
        return {"error": f"No location found matching '{location_keyword}'."}
    if len(matches) > 1:
        exact = [b for b in matches if (b.get("LOCATION") or "").strip().lower() == kw]
        if len(exact) == 1:
            matches = exact
        else:
            names = ", ".join(b["LOCATION"] for b in matches)
            return {"error": f"Multiple locations match '{location_keyword}': {names}."}

    return {"bill_date": result["bill_date"], "branch": matches[0]}


def format_reconciliation_card_fields(branch_row: dict) -> list:
    """
    Turns one branch's raw dict into (label, value) pairs using the
    real printed-report field names, skipping zero/None values to
    keep the card readable — matches the printed PDF's own convention
    of showing every line, but a chat card benefits from omitting the
    genuinely-zero ones rather than listing 20 "₹0" lines.
    """
    pairs = []
    for col, label in _REPORT_LABELS.items():
        val = branch_row.get(col)
        if val is None:
            continue
        try:
            val = float(val)
        except (TypeError, ValueError):
            continue
        if val == 0:
            continue
        pairs.append((label, val))
    return pairs