"""
Read-only reproduction of dbo.LabDayCollection_All's financial output.
Never executes the source procedure (which writes client LIS tables).
Source: previously provided SQL Server CREATE PROCEDURE text.
These queries cannot prove live parity; verify against an existing LIS export
using tools/verify_recon_parity.py (offline reference comparison only).

Important source quirk retained: COMPADVCC filters the hard-coded date
19 FEB 2022, rather than the requested bill date. This matches the source
procedure but needs a separate, authorized business-rule correction upstream.
"""

from datetime import datetime, timedelta

from database.connection import get_hospital_connection


import re as _re_iso


def _iso_to_date(params):
    """'YYYY-MM-DD' strings -> date objects so SQL Server never re-parses them with a day-first DATEFORMAT."""
    from datetime import date as _d
    out = []
    for p in (params if isinstance(params, (tuple, list)) else (params,)):
        if isinstance(p, str) and _re_iso.fullmatch(r"\d{4}-\d{2}-\d{2}", p):
            p = _d.fromisoformat(p)
        out.append(p)
    return tuple(out)


def _resolve_relative_date(value: str) -> str:
    v = (value or "").strip().lower()
    today = datetime.now().date()
    if v == "today":
        return today.isoformat()
    if v == "yesterday":
        return (today - timedelta(days=1)).isoformat()
    return value


class ReconUnavailable(Exception):
    """The reconciliation cannot be computed exactly for this client; callers must show an error, never a partial number."""


def _compute_one_location(cursor, location_id: str, bill_date: str) -> dict:
    """Runs the SP's per-location formula as pure SELECTs, no writes."""

    def scalar(sql, params):
        cursor.execute(sql, _iso_to_date(params))
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
          AND CONVERT(DATE, B.BILLDATE, 101) < CONVERT(DATE, ?, 23) AND A.STATUS = 'R'
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

    prevdue_cheque = scalar(
        """
        SELECT SUM(ISNULL(A.PAIDAMOUNT,0))
        FROM trnMODEOFCOLLECTIONSDET A, trnINVLABPRI B
        WHERE CONVERT(DATETIME, CONVERT(VARCHAR, A.DATEOFBILL, 106)) = CONVERT(DATETIME, ?, 23)
          AND A.TYPE IN ('DUE PAYMENT') AND A.LOCATIONID = ?
          AND A.PREVIOUSBILLNO = B.BILLNO AND A.STATUS = 'P'
          AND CONVERT(DATE, B.BILLDATE, 106) < CONVERT(DATE, ?, 23)
          AND A.MODE IN ('CHEQUE')
        """,
        (bill_date, location_id, bill_date),
    )

    prevdue_dd = scalar(
        """
        SELECT SUM(ISNULL(A.PAIDAMOUNT,0))
        FROM trnMODEOFCOLLECTIONSDET A, trnINVLABPRI B
        WHERE CONVERT(DATETIME, CONVERT(VARCHAR, A.DATEOFBILL, 106)) = CONVERT(DATETIME, ?, 23)
          AND A.TYPE IN ('DUE PAYMENT') AND A.LOCATIONID = ?
          AND A.PREVIOUSBILLNO = B.BILLNO AND A.STATUS = 'P'
          AND CONVERT(DATE, B.BILLDATE, 106) < CONVERT(DATE, ?, 23)
          AND A.MODE IN ('DD')
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

    # TOTALDUES - exactly the real procedure's expression (LabDayCollection step 3). dbo.DUEREC / SEC_CONC / CCDUEAMT are
    # SQL Server scalar functions; SQL Server forbids scalar functions from modifying tables, so calling them is read-only.
    # The procedure stores each function result in NUMERIC(12,0), hence the same CONVERT here.
    try:
        total_dues = scalar(
            """
            SELECT (SUM(ISNULL(A.DUEAMOUNT,0))
                    - (ISNULL(CONVERT(NUMERIC(12,0), dbo.DUEREC(CONVERT(DATE, ?), ?)),0)
                       + ISNULL(CONVERT(NUMERIC(12,0), dbo.SEC_CONC(CONVERT(DATE, ?), ?)),0)))
                   - ISNULL(CONVERT(NUMERIC(12,0), dbo.CCDUEAMT(CONVERT(DATE, ?), ?)),0)
            FROM trnMODEOFCOLLECTIONSDET A, trnINVLABPRI B
            WHERE A.BILLNO = B.BILLNO AND CONVERT(DATE, A.DATEOFBILL, 106) = ?
              AND A.TYPE IN ('OPLAB') AND A.STATUS = 'P' AND A.LOCATIONID = ?
              AND B.CREDITBILL = 'False'
            """,
            (bill_date, location_id, bill_date, location_id, bill_date, location_id, bill_date, location_id),
        )
    except Exception as e:
        # Never guess: without the due functions the cash-in-hand figure would be wrong. Fail the whole report visibly.
        raise ReconUnavailable(f"Dues could not be calculated for {location_id} ({type(e).__name__}); "
                               "this client's database may not have dbo.DUEREC / SEC_CONC / CCDUEAMT.") from e

    def comp_advance(modes, pay_date):
        # Query intentionally reproduces the source SP's organisation-type,
        # payment header and mode filters. Date for credit card is hard-coded
        # in the source SP; do not silently alter its accounting semantics.
        placeholders = ','.join('?' for _ in modes)
        try:
            return scalar(
                f"""
                SELECT SUM(ISNULL(B.PaidAmt,0))
                FROM mstOrganisation A, trnCompPayments B
                WHERE A.ORGANISATIONCODE = B.ORGCODE
                  AND A.COMPTYPE NOT IN ('CC') AND B.LocationID = ?
                  AND B.PayTypeHeader IN ('Payment','Wrong Entry')
                  AND B.MODE IN ({placeholders})
                  AND CONVERT(DATE, B.PayDate, 106) = CONVERT(DATE, ?, 23)
                """,
                (location_id, *modes, pay_date),
            )
        except Exception as e:
            raise ReconUnavailable(
                f"Corporate advances could not be calculated for {location_id} "
                f"({type(e).__name__}); cannot safely show a financial total."
            ) from e

    compadv_cash = comp_advance(('CASH',), bill_date)
    compadv_cc = comp_advance(('Credit Card',), '2022-02-19')  # source SP hardcoded date
    compadv_upi = comp_advance(('UPI',), bill_date)
    compadv_chq = comp_advance(('Cheque',), bill_date)
    compadv_rtgs = comp_advance(('RTGS', 'RTGS/NEFT'), bill_date)
    compadv_app = comp_advance(('APP',), bill_date)

    total_bills = scalar(
        """
        SELECT COUNT(*) FROM trnINVLABPRI A
        WHERE A.STATUS IS NULL AND A.LOCATIONID = ? AND CONVERT(DATE, A.BILLDATE, 106) = ?
        """,
        (location_id, bill_date),
    )

    total_online_upi = total_cheque + total_upi
    core_business_cash = (
        total_cash - total_dues - total_concessions - total_creditcards
        - total_cheque - total_upi - total_refunds - total_refunds_prev - total_exp
    )
    cash_in_hand = core_business_cash + prevdue_cash + compadv_cash
    # The source SP does not add PREVDUE_UPI to TOTALCHQONLINEUPI.
    chq_online_upi_received = total_online_upi

    return {
        "GTOTALCREDITS": gtotalcredits,
        "TOTALCASH": total_cash,
        "TOTALCREDITS": total_credits,
        "TOTALDUES": total_dues,
        "TOTALCONCESSIONS": total_concessions,
        "TOTALCREDITCARDS": total_creditcards,
        "TOTALCHEQUE": total_cheque,
        "TOTALUPI": total_upi,
        "TOTALONLINEUPI": total_online_upi,
        "TOTALREFUND": total_refunds,
        "TOTALREFUNDSPREV": total_refunds_prev,
        "EXPENDITURE": total_exp,
        "TOTALCOREBUSINESSCASH": core_business_cash,
        "PREVDUE_CASH": prevdue_cash,
        "PREVDUE_CREDITS": prevdue_credits,
        "PREVDUE_CHEQUE": prevdue_cheque,
        "PREVDUE_DD": prevdue_dd,
        "PREVDUE_UPI": prevdue_upi,
        "COMPADVCASH": compadv_cash,
        "COMPADVCC": compadv_cc,
        "COMPADVUPI": compadv_upi,
        "COMPADVCHQ": compadv_chq,
        "COMPADVRTGS": compadv_rtgs,
        "COMPADVAPP": compadv_app,
        "TOTALCASHRECEIVED": core_business_cash + prevdue_cash,
        "TOTALCCRECEIVED": total_creditcards + prevdue_credits,
        "TOTALCHQONLINEUPI": chq_online_upi_received,
        "TOTALCASHINHAND": cash_in_hand,
        "TOTALCCINHAND": total_creditcards + prevdue_credits + compadv_cc,
        "TOTALCHQINHAND": total_cheque + prevdue_cheque + compadv_chq,
        "TOTALONLINEUPIINHAND": total_upi + prevdue_dd + prevdue_upi + compadv_upi,
        "TOTALBILLS": total_bills,
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
    except ReconUnavailable as e:
        return {"error": str(e)}
    except Exception as e:
        return {"error": f"Query failed: {e}"}
    finally:
        conn.close()