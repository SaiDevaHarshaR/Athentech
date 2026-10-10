"""Read-only payment-mode collection pivot for institutions with differing LIS schemas.

This is NOT the LabDayCollection_All cash reconciliation. In particular,
TOTALAMOUNT may be billed value rather than settled receipts; when chosen it is
prominently labelled in generated workbooks so it cannot be confused with cash.
"""

import re

from database.connection import get_hospital_connection

_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _identifier(value):
    if not value or not _IDENTIFIER.fullmatch(value):
        raise ValueError("Unsafe or unsupported database column name")
    return "[" + value + "]"


def _columns(cursor, table):
    cursor.execute(
        "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = ?",
        (table,),
    )
    return {str(row[0]).upper(): str(row[0]) for row in cursor.fetchall()}


def _pick(columns, *names):
    for name in names:
        if name in columns:
            return _identifier(columns[name])
    return None


def collection_mode_data(date_from, date_to, db_name, db_server=None,
                         db_user=None, db_password=None, location_keyword=None):
    """Read payment-mode summary with discovered per-institution columns.

    Returns rows of (branch, mode, amount). Does not execute procedures, write
    to the institution DB, or silently call a billed value 'cash receipts'.
    """
    conn = get_hospital_connection(db_name, db_server, db_user, db_password)
    if not conn:
        return {"error": "Could not connect to the hospital database."}

    try:
        cur = conn.cursor()
        cols = _columns(cur, "trnMODEOFCOLLECTIONSDET")
        if not cols:
            return {"error": "Collection table trnMODEOFCOLLECTIONSDET was not found in this institution."}
        date_col = _pick(cols, "DATEOFBILL", "BILLDATE", "TRNDATE")
        mode_col = _pick(cols, "MODE", "PAYMENTMODE", "PAYMODE")
        paid_col = _pick(cols, "PAIDAMOUNT", "PAIDAMT", "PAID")
        total_col = _pick(cols, "TOTALAMOUNT", "TOTALCHARGES", "GRANDTOTAL", "AMOUNT")
        loc_col = _pick(cols, "LOCATIONID", "LOCID", "BRANCHID")
        if not date_col or not mode_col or not (paid_col or total_col):
            return {"error": "Collection table lacks a recognized date, payment mode, or amount column."}

        # Resolve the amount per record, NOT per day/institution.
        # A nonzero PAIDAMOUNT remains authoritative for that record;
        # when it is zero or null, use TOTALAMOUNT where available.
        paid_numeric = (f"TRY_CONVERT(decimal(19,2), m.{paid_col})" if paid_col else "NULL")
        total_numeric = (f"TRY_CONVERT(decimal(19,2), m.{total_col})" if total_col else "NULL")
        amount_expr = (
            f"CASE WHEN COALESCE({paid_numeric}, 0) <> 0 THEN {paid_numeric} "
            f"ELSE COALESCE({total_numeric}, 0) END"
            if paid_col and total_col else
            f"COALESCE({paid_numeric if paid_col else total_numeric}, 0)"
        )
        cur.execute(
            f"SELECT COUNT_BIG(*), "
            f"SUM(CASE WHEN COALESCE({paid_numeric}, 0) <> 0 THEN 1 ELSE 0 END), "
            f"SUM(CASE WHEN COALESCE({paid_numeric}, 0) = 0 "
            f"AND COALESCE({total_numeric}, 0) <> 0 THEN 1 ELSE 0 END) "
            f"FROM trnMODEOFCOLLECTIONSDET m "
            f"WHERE m.{date_col} >= ? AND m.{date_col} < ?",
            (date_from, date_to),
        )
        stats = cur.fetchone()
        count = int(stats[0] or 0) if stats else 0
        nonzero_paid_rows = int(stats[1] or 0) if stats else 0
        fallback_rows = int(stats[2] or 0) if stats else 0
        if not count:
            return {"error": f"No collection entries between {date_from} and {date_to}."}

        metric = ("mixed" if nonzero_paid_rows and fallback_rows else
                  "recorded_total" if fallback_rows else "paid")
        source_label = (
            f"{paid_col.strip('[]')} / {total_col.strip('[]')} (row-level fallback)"
            if paid_col and total_col else
            (paid_col or total_col).strip('[]')
        )

        join = ""
        branch_expr = "'All locations'"
        if loc_col:
            branch_expr = f"COALESCE(CONVERT(nvarchar(100), m.{loc_col}), 'Unknown')"
            location_cols = _columns(cur, "mstLocation")
            loc_id = _pick(location_cols, "LOCATIONID")
            loc_name = _pick(location_cols, "LOCATIONNAME")
            if loc_id and loc_name:
                join = (f" LEFT JOIN mstLocation l ON "
                        f"CONVERT(nvarchar(100), m.{loc_col}) = "
                        f"CONVERT(nvarchar(100), l.{loc_id})")
                branch_expr = (f"COALESCE(NULLIF(LTRIM(RTRIM(l.{loc_name})), ''), "
                               f"CONVERT(nvarchar(100), m.{loc_col}), 'Unknown')")

        cur.execute(
            f"SELECT {branch_expr} AS Branch, "
            f"COALESCE(NULLIF(UPPER(LTRIM(RTRIM(CONVERT(nvarchar(100), m.{mode_col})))), ''), 'UNKNOWN') AS Mode, "
            f"SUM({amount_expr}) AS Amount "
            f"FROM trnMODEOFCOLLECTIONSDET m{join} "
            f"WHERE m.{date_col} >= ? AND m.{date_col} < ? "
            f"GROUP BY {branch_expr}, "
            f"COALESCE(NULLIF(UPPER(LTRIM(RTRIM(CONVERT(nvarchar(100), m.{mode_col})))), ''), 'UNKNOWN') "
            f"ORDER BY Branch, Mode",
            (date_from, date_to),
        )
        rows = [(str(r[0] or "Unknown"), str(r[1] or "UNKNOWN"), float(r[2] or 0))
                for r in cur.fetchall()]
        if location_keyword:
            keyword = location_keyword.strip().casefold()
            names = sorted({r[0] for r in rows if keyword in r[0].casefold()})
            exact = [name for name in names if name.strip().casefold() == keyword]
            if exact:
                names = exact
            if not names:
                return {"error": f"No collection for branch '{location_keyword}' in this period."}
            if len(names) != 1:
                return {"error": "Multiple matching branches: " + ", ".join(names[:8])}
            rows = [r for r in rows if r[0] == names[0]]

        if not rows:
            return {"error": "No collection records found for this selection."}

        return {
            "rows": rows,
            "amount_column": source_label,
            "metric": metric,
            "fallback_rows": fallback_rows,
            "paid_rows": nonzero_paid_rows,
            "warning": (
                f"Per-record amount selection: {nonzero_paid_rows} rows use non-zero PAIDAMOUNT; "
                f"{fallback_rows} rows use TOTALAMOUNT because PAIDAMOUNT was zero/null. "
                "TOTALAMOUNT may be billed value rather than received money: "
                "this is a mixed/recorded-value report, not verified cash reconciliation. "
                "Confirm each client's accounting semantics before using as revenue."
                if fallback_rows else
                "Amounts use PAIDAMOUNT; verify refund/status handling against official reconciliation."
            ),
        }
    except Exception as exc:
        return {"error": f"Institution collection query failed: {exc}"}
    finally:
        conn.close()
