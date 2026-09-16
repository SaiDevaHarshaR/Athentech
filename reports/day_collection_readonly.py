"""
Read-only equivalent of dbo.LabDayCollection_All — same confirmed
formula, computed via pure SELECT queries instead of EXEC'ing the real
stored procedure (which performs a real DELETE+INSERT into
trnTempDayCollAll). Use this for Excel export and any other read-only
reporting need; use the real SP (day_collection_reconciliation.py) only
when the live, cached report screen behavior is specifically required.

Every formula fragment below is copied directly from the confirmed real
procedure body — same WHERE clauses, same column names, same logic.
"""

from datetime import datetime, timedelta

from database.connection import get_hospital_connection


def _resolve_relative_date(value: str) -> str:
    v = (value or "").strip().lower()
    today = datetime.now().date()
    if v == "today":
        return today.isoformat()
    if v == "yesterday":
        return (today - timedelta(days=1)).isoformat()
    return value


def _compute_one_location(cursor, location_id: str, bill_date: str) -> dict:
    """Runs the SP's per-location formula as pure SELECTs, no writes."""

    def scalar(sql, params):
        cursor.execute(sql, params)
        row = cursor.fetchone()
        return float(row[0]) if row and row[0] is not None else 0.0

    total_cash = scalar(
        """
        SELECT SUM(ISNULL(B.TOTALAMOUNT,0)) + ISNULL((
            SELECT SUM(ISNULL(A2.TOTALCHARGES,0))
            FROM trnINVLABPRI A2, mstOrganisation C
            WHERE A2.ORGANISATIONCODE = C.ORGANISATIONCODE AND A2.STATUS IS NULL
              AND A2.LOCATIONID = ? AND A2.PAYTYPE = 'COMPANY'
              AND CONVERT(DATE, A2.BILLDATE, 106) = ?
              AND A2.CREDITBILL = 'False' AND C.COMPTYPE NOT IN ('CC')
        ), 0)
        FROM trnINVLABPRI A, trnMODEOFCOLLECTIONSDET B
        WHERE A.BILLNO = B.BILLNO AND B.STATUS = 'P'
          AND CONVERT(DATE, A.BILLDATE, 106) = ? AND B.TYPE = 'OPLAB'
          AND A.LOCATIONID = ? AND A.PAYTYPE = 'PAYING'
        """,
        (location_id, bill_date, bill_date, location_id),
    )

    total_credits = scalar(
        """
        SELECT SUM(ISNULL(B.CHARGE,0))
        FROM trnINVLABPRI A, trnINVLABDET B
        WHERE A.BILLNO = B.BILLNO AND A.STATUS IS NULL
          AND CONVERT(DATE, A.BILLDATE, 106) = ? AND A.LOCATIONID = ?
          AND A.PAYTYPE = 'COMPANY' AND A.CREDITBILL = 'True'
        """,
        (bill_date, location_id),
    )

    total_concessions = scalar(
        """
        SELECT SUM(ISNULL(A.CONCESSIONAMOUNT,0))
        FROM trnMODEOFCOLLECTIONSDET A, trnINVLABPRI B
        WHERE A.BILLNO = B.BILLNO AND CONVERT(DATE, A.DATEOFBILL, 106) = ?
          AND A.TYPE IN ('OPLAB','LabConcession2') AND A.LOCATIONID = ?
          AND A.STATUS = 'P' AND CONVERT(DATE, B.BILLDATE, 106) = ?
        """,
        (bill_date, location_id, bill_date),
    )

    total_creditcards = scalar(
        """
        SELECT SUM(ISNULL(A.PAIDAMOUNT,0))
        FROM trnMODEOFCOLLECTIONSDET A, trnINVLABPRI B
        WHERE CONVERT(DATE, A.DATEOFBILL, 106) = ? AND A.TYPE IN ('OPLAB','DUE PAYMENT')
          AND A.MODE IN ('CREDITCARD') AND A.STATUS = 'P' AND A.LOCATIONID = ?
          AND A.BILLNO = B.BILLNO AND CONVERT(DATE, B.BILLDATE, 106) = ?
        """,
        (bill_date, location_id, bill_date),
    )

    total_cheque = scalar(
        """
        SELECT SUM(ISNULL(A.PAIDAMOUNT,0))
        FROM trnMODEOFCOLLECTIONSDET A, trnINVLABPRI B
        WHERE CONVERT(DATE, A.DATEOFBILL, 106) = ? AND A.TYPE IN ('OPLAB','DUE PAYMENT')
          AND A.MODE IN ('CHEQUE') AND A.STATUS = 'P' AND A.LOCATIONID = ?
          AND A.BILLNO = B.BILLNO AND CONVERT(DATE, B.BILLDATE, 106) = ?
        """,
        (bill_date, location_id, bill_date),
    )

    total_upi = scalar(
        """
        SELECT SUM(ISNULL(A.PAIDAMOUNT,0))
        FROM trnMODEOFCOLLECTIONSDET A, trnINVLABPRI B
        WHERE CONVERT(DATE, A.DATEOFBILL, 106) = ? AND A.TYPE IN ('OPLAB','DUE PAYMENT')
          AND A.MODE IN ('DD','UPI','ONLINE') AND A.STATUS = 'P' AND A.LOCATIONID = ?
          AND A.BILLNO = B.BILLNO AND CONVERT(DATE, B.BILLDATE, 106) = ?
        """,
        (bill_date, location_id, bill_date),
    )

    total_refunds = scalar(
        """
        SELECT SUM(ISNULL(A.PAIDAMOUNT,0))
        FROM trnMODEOFCOLLECTIONSDET A, trnINVLABPRI B
        WHERE CONVERT(DATE, A.DATEOFBILL, 106) = ? AND A.TYPE IN ('LabRefund')
          AND A.LOCATIONID = ? AND A.STATUS = 'R' AND A.PREVIOUSBILLNO = B.BILLNO
          AND CONVERT(DATE, B.BILLDATE, 106) = ?
        """,
        (bill_date, location_id, bill_date),
    )

    total_refunds_prev = scalar(
        """
        SELECT SUM(ISNULL(A.PAIDAMOUNT,0))
        FROM trnMODEOFCOLLECTIONSDET A, trnINVLABPRI B
        WHERE CONVERT(DATE, A.DATEOFBILL, 106) = ? AND A.TYPE IN ('LabRefund')
          AND A.LOCATIONID = ? AND A.PREVIOUSBILLNO = B.BILLNO
          AND CONVERT(VARCHAR(10), B.BILLDATE, 101) < ? AND A.STATUS = 'R'
        """,
        (bill_date, location_id, bill_date),
    )

    total_exp = scalar(
        """
        SELECT ISNULL(SUM(A.PAIDAMT),0) - ((
            SELECT ISNULL(SUM(A2.PAIDAMT),0) FROM trnVoucherGen A2
            WHERE CONVERT(DATE, A2.TRNDATE, 106) = ? AND A2.LOCATIONID = ? AND A2.TYPE = 'Credit'
        ))
        FROM trnVoucherGen A
        WHERE CONVERT(DATE, A.TRNDATE, 106) = ? AND A.LOCATIONID = ? AND A.TYPE = 'Debit'
        """,
        (bill_date, location_id, bill_date, location_id),
    )

    prevdue_cash = scalar(
        """
        SELECT SUM(ISNULL(A.PAIDAMOUNT,0))
        FROM trnMODEOFCOLLECTIONSDET A, trnINVLABPRI B
        WHERE CONVERT(DATE, A.DATEOFBILL, 106) = ? AND A.TYPE IN ('DUE PAYMENT')
          AND A.LOCATIONID = ? AND A.PREVIOUSBILLNO = B.BILLNO AND A.STATUS = 'P'
          AND CONVERT(DATE, B.BILLDATE, 106) < ? AND A.MODE IN ('CASH')
        """,
        (bill_date, location_id, bill_date),
    )

    prevdue_credits = scalar(
        """
        SELECT SUM(ISNULL(A.PAIDAMOUNT,0))
        FROM trnMODEOFCOLLECTIONSDET A, trnINVLABPRI B
        WHERE CONVERT(DATE, A.DATEOFBILL, 106) = ? AND A.TYPE IN ('DUE PAYMENT')
          AND A.LOCATIONID = ? AND A.PREVIOUSBILLNO = B.BILLNO AND A.STATUS = 'P'
          AND CONVERT(DATE, B.BILLDATE, 106) < ? AND A.MODE IN ('CREDITCARD')
        """,
        (bill_date, location_id, bill_date),
    )

    prevdue_upi = scalar(
        """
        SELECT SUM(ISNULL(A.PAIDAMOUNT,0))
        FROM trnMODEOFCOLLECTIONSDET A, trnINVLABPRI B
        WHERE CONVERT(DATE, A.DATEOFBILL, 106) = ? AND A.TYPE IN ('DUE PAYMENT')
          AND A.LOCATIONID = ? AND A.PREVIOUSBILLNO = B.BILLNO AND A.STATUS = 'P'
          AND CONVERT(DATE, B.BILLDATE, 106) < ? AND A.MODE IN ('UPI','ONLINE')
        """,
        (bill_date, location_id, bill_date),
    )

    gtotalcredits = scalar(
        """
        SELECT SUM(ISNULL(B.TOTALAMOUNT,0))
        FROM trnINVLABPRI A, trnMODEOFCOLLECTIONSDET B
        WHERE A.BILLNO = B.BILLNO AND A.STATUS IS NULL
          AND CONVERT(DATE, A.BILLDATE, 106) = ? AND A.LOCATIONID = ? AND B.TYPE = 'OPLAB'
        """,
        (bill_date, location_id),
    )

    total_online_upi = total_cheque + total_upi
    core_business_cash = (
        total_cash - total_concessions - total_creditcards
        - total_cheque - total_upi - total_refunds - total_refunds_prev - total_exp
    )
    # NOTE: TOTALDUES omitted here — its real formula calls SQL scalar
    # functions (dbo.DUEREC, dbo.SEC_CONC, dbo.CCDUEAMT) not reproduced
    # in pure SELECT form. Confirm with AthenTech whether these functions
    # are themselves read-only before adding this field — call them
    # directly (SELECT dbo.DUEREC(...)) if so, same as any other scalar
    # function, still no write involved either way.
    cash_in_hand = core_business_cash + prevdue_cash
    chq_online_upi_received = total_online_upi + prevdue_upi

    return {
        "GTOTALCREDITS": gtotalcredits,
        "TOTALCASH": total_cash,
        "TOTALCREDITS": total_credits,
        "TOTALCONCESSIONS": total_concessions,
        "TOTALCREDITCARDS": total_creditcards,
        "TOTALONLINEUPI": total_online_upi,
        "TOTALREFUND": total_refunds,
        "TOTALREFUNDSPREV": total_refunds_prev,
        "EXPENDITURE": total_exp,
        "TOTALCOREBUSINESSCASH": core_business_cash,
        "PREVDUE_UPI": prevdue_upi,
        "TOTALCASHRECEIVED": core_business_cash + prevdue_cash,
        "TOTALCCRECEIVED": total_creditcards + prevdue_credits,
        "TOTALCHQONLINEUPI": chq_online_upi_received,
        "TOTALCASHINHAND": cash_in_hand,
        "TOTALCCINHAND": total_creditcards + prevdue_credits,
        "TOTALCHQINHAND": total_cheque,
        "TOTALONLINEUPIINHAND": total_upi + prevdue_upi,
    }


def get_day_collection_all_branches_readonly(
    bill_date: str,
    db_name: str,
    db_server=None, db_user=None, db_password=None,
) -> dict:
    """
    Same output shape as day_collection_reconciliation.py's
    get_day_collection_all_branches, but pure SELECT — no EXEC, no
    write to trnTempDayCollAll or anywhere else. Slower (many small
    queries per location instead of one SP call) but genuinely
    read-only, safe for Excel export or any reporting path that
    shouldn't touch the database at all.
    """
    bill_date = _resolve_relative_date(bill_date)

    conn = get_hospital_connection(db_name, db_server, db_user, db_password)
    if not conn:
        return {"error": "Could not connect to the hospital database."}

    try:
        cursor = conn.cursor()
        cursor.execute("SELECT LOCATIONID, LOCATIONNAME FROM mstLocation WHERE ACTIVE = 1")
        locations = cursor.fetchall()

        branches = []
        for loc_id, loc_name in locations:
            values = _compute_one_location(cursor, loc_id, bill_date)
            values["LOCATION"] = loc_name
            values["LOCATIONID"] = loc_id
            branches.append(values)

        return {"bill_date": bill_date, "branches": branches}
    except Exception as e:
        return {"error": f"Query failed: {e}"}
    finally:
        conn.close()