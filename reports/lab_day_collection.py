"""
Calls the REAL stored procedure dbo.LabDayCollection directly, instead
of trying to reconstruct its logic from raw table queries — confirmed
via the actual procedure definition (AthenTech-provided) that this is
~30 separate SELECT statements, several calling OTHER stored functions
(DUEREC, SEC_CONC, CCDUEAMT, CC_CREDIT, DUERECDtls, SEC_CONCDtls, ...)
whose definitions aren't available — genuinely not reconstructable
from outside. Confirmed entirely SELECT-only internally (no INSERT/
UPDATE/DELETE anywhere in the procedure body) — safe to call as a
real read-only operation, not a write.

Takes a raw LOCATIONID code (e.g. 'LOC04') — name resolution now
happens one layer up, in agent/tools.py's get_lab_day_collection, via
mstlocation (the confirmed real location master table).
"""

import re

from database.connection import get_hospital_connection


# The @ACTIVITY='Lab' branch of the procedure returns MANY result sets
# in sequence (confirmed from the real procedure body) — this labels
# the first several, which cover the core reconciliation figures. Later
# result sets (InvoicePayments/CCPayments/CC-client breakdowns) exist
# too but aren't labeled here yet.
_LAB_RESULT_SET_LABELS = [
    "Gross paying bills (status open)",
    "Paid amount — direct patient payments",
    "Company credit bills",
    "Due amount (net of previous dues received)",
    "Concession amount",
    "Credit card collected",
    "Cheque/DD/UPI/Online collected",
    "Refund amount (same-day bill)",
    "Refund amount (previous bill)",
    "Expenditure (debit minus credit vouchers)",
    "Previous due received — cash",
    "Previous due received — credit card",
]


def call_lab_day_collection(
    location_id: str,
    bill_date: str,
    db_name: str,
    db_server=None, db_user=None, db_password=None,
) -> dict:
    """
    Calls dbo.LabDayCollection with @ACTIVITY='Lab' for one specific
    location and one specific date (YYYY-MM-DD). Returns the labeled
    result sets as a dict — real, authoritative figures, not a
    reconstruction.

    CONFIRMED (real procedure body): the 'Lab' activity is SINGLE-DAY
    ONLY — every branch compares BILLDATE = @billdate, never a range.
    There is no way to get a "this year"/"this month" total from this
    activity — a real bug already happened where a broader period got
    silently answered with just one day's figures under a wrong label.
    This function refuses anything that isn't a real single date
    rather than repeat that.
    """
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", bill_date):
        return {
            "error": (
                f"'{bill_date}' is not a single real date (YYYY-MM-DD). "
                "This reconciliation is confirmed SINGLE-DAY ONLY in the real stored "
                "procedure — there is no way to get a 'this year'/'this month' total "
                "from it. If a period total is genuinely needed, that would require "
                "calling this once per day in the range and summing results — not "
                "supported yet. Ask for one specific date instead."
            )
        }

    conn = get_hospital_connection(db_name, db_server, db_user, db_password)
    if not conn:
        return {"error": "Could not connect to the hospital database."}

    try:
        cursor = conn.cursor()
        cursor.execute(
            "EXEC dbo.LabDayCollection "
            "@FROMDATE=?, @TODATE=?, @LOCATIONID=?, @billdate=?, @BILLNO=NULL, @ACTIVITY=?",
            (bill_date, bill_date, location_id, bill_date, "Lab"),
        )

        results = []
        has_set = True
        while has_set:
            try:
                columns = [c[0] for c in cursor.description] if cursor.description else []
                rows = cursor.fetchall()
                results.append({"columns": columns, "rows": [list(r) for r in rows]})
            except Exception:
                results.append({"columns": [], "rows": []})
            has_set = cursor.nextset()

        labeled = {}
        for i, label in enumerate(_LAB_RESULT_SET_LABELS):
            if i < len(results):
                r = results[i]
                labeled[label] = r["rows"][0] if r["rows"] else None

        return {
            "location_id": location_id,
            "bill_date": bill_date,
            "labeled_results": labeled,
            "raw_result_set_count": len(results),
        }
    except Exception as e:
        return {"error": f"Procedure call failed: {e}"}
    finally:
        conn.close()