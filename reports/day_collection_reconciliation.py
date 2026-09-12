"""
Real cash/day-collection reconciliation — calls dbo.LabDayCollection_All
directly (the actual stored procedure, confirmed via its real source
code). This REPLACES the old lab_day_collection.py approach, which
called a different, less complete procedure (dbo.LabDayCollection) and
required manual field-by-field guessing to match a real printed report.

Confirmed from source: LabDayCollection_All, with @ACTIVITY='GetDetails',
loops over EVERY active location (mstLocation WHERE ACTIVE=1) in one
execution, computes the full real reconciliation formula for each, and
returns them all as one result set (via SELECT * FROM trnTempDayCollAll
WHERE USERID=? AND BILLDATE=?, the procedure's own final step). This
naturally gives an all-branches view for free — no extra looping needed.

Single-day only, same confirmed constraint as before — @BILLDATE is a
single date parameter, no range support in the procedure itself.

The USERID parameter scopes the procedure's internal DELETE+INSERT
(trnTempDayCollAll rows for that USERID+BILLDATE get replaced each
call) — using a fixed, dedicated ID for this agent's own calls avoids
colliding with real staff usage of the same underlying report screen.
"""

import re
from datetime import datetime, timedelta

from database.connection import get_hospital_connection

_AGENT_USERID = "sahasra_ai_agent"

# Real column order from trnTempDayCollAll, confirmed from the actual
# procedure's INSERT statement — used to label the raw row tuple.
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
    """
    Returns the real, complete reconciliation for EVERY active location
    on one date, straight from LabDayCollection_All. bill_date:
    'YYYY-MM-DD', 'today', or 'yesterday'.
    """
    bill_date = _resolve_relative_date(bill_date)
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", bill_date):
        return {"error": f"'{bill_date}' is not a real single date (YYYY-MM-DD). This is single-day only."}

    conn = get_hospital_connection(db_name, db_server, db_user, db_password)
    if not conn:
        return {"error": "Could not connect to the hospital database."}

    try:
        cursor = conn.cursor()
        # NOCOUNT stops rowcount messages that confuse pyodbc
        cursor.execute("SET NOCOUNT ON")
        cursor.execute(
            "EXEC dbo.LabDayCollection_All @USERID=?, @BILLDATE=?, @ACTIVITY='GetDetails'",
            (_AGENT_USERID, bill_date),
        )
        # Skip intermediate result sets until we get a real SELECT
        rows = []
        while True:
            if cursor.description is not None:
                rows = cursor.fetchall()
                break
            if not cursor.nextset():
                break
        branches = [dict(zip(_COLUMNS, row)) for row in rows]
        return {"bill_date": bill_date, "branches": branches}
    except Exception as e:
        return {"error": f"Procedure call failed: {e}"}
    finally:
        conn.close()

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