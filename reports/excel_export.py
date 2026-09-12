"""
Excel exports.
- day / week → multi-branch + GRAND TOTAL + overall mode totals
- month / year → single branch only (location required)
Row 1 = hospital/diagnostics name only.
"""

import re
from datetime import date, timedelta
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter

from database.connection import get_hospital_connection


def _period_dates(period_keyword: str):
    today = date.today()
    p = (period_keyword or "today").lower().replace(" ", "_")
    if p == "yesterday":
        d = today - timedelta(days=1)
        return d.isoformat(), (d + timedelta(days=1)).isoformat(), "Yesterday"
    if p in ("this_week", "thisweek", "week"):
        start = today - timedelta(days=today.weekday())
        return start.isoformat(), (today + timedelta(days=1)).isoformat(), "This Week"
    if p in ("last_week", "lastweek"):
        start = today - timedelta(days=today.weekday() + 7)
        return start.isoformat(), (start + timedelta(days=7)).isoformat(), "Last Week"
    if p in ("this_month", "thismonth", "month"):
        start = today.replace(day=1)
        return start.isoformat(), (today + timedelta(days=1)).isoformat(), "This Month"
    if p in ("last_month", "lastmonth"):
        first_this = today.replace(day=1)
        last_start = (first_this - timedelta(days=1)).replace(day=1)
        return last_start.isoformat(), first_this.isoformat(), "Last Month"
    if p in ("this_year", "thisyear", "year"):
        start = today.replace(month=1, day=1)
        return start.isoformat(), (today + timedelta(days=1)).isoformat(), "This Year"
    return today.isoformat(), (today + timedelta(days=1)).isoformat(), "Today"


def _is_multi_branch(period: str) -> bool:
    p = (period or "today").lower().replace(" ", "_")
    return p in (
        "today", "yesterday", "day",
        "this_week", "thisweek", "week",
        "last_week", "lastweek",
    )


def _mode_bucket(mode: str) -> str:
    m = (mode or "").upper().strip()
    if "CASH" in m:
        return "CASH"
    if any(x in m for x in ("UPI", "ONLINE", "PHONEPE", "GPAY", "PAYTM")):
        return "UPI_ONLINE"
    if any(x in m for x in ("CARD", "CREDIT CARD", "DEBIT")):
        return "CARD"
    if any(x in m for x in ("CHEQUE", "CHECK", "DD")):
        return "CHEQUE"
    if "CREDIT" in m:
        return "CREDIT"
    return "OTHER"


def _title_row(ws, hospital_name: str, col_span: int) -> int:
    name = (hospital_name or "Hospital").strip() or "Hospital"
    cell = ws.cell(row=1, column=1, value=name)
    cell.font = Font(bold=True, size=14, name="Arial", color="1F4E79")
    if col_span > 1:
        ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=max(col_span, 2))
    return 2


def _style_header(ws, row: int, headers: list):
    font = Font(bold=True, color="FFFFFF", name="Arial")
    fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
    for col, h in enumerate(headers, start=1):
        c = ws.cell(row=row, column=col, value=h)
        c.font = font
        c.fill = fill
        c.alignment = Alignment(horizontal="center")


def _save(wb, filename: str, period_label: str) -> dict:
    bio = BytesIO()
    wb.save(bio)
    bio.seek(0)
    return {"file": bio, "filename": filename, "period_label": period_label}


def _export_multi_branch_mode_pivot(
    period, db_name, db_server=None, db_user=None, db_password=None, hospital_name="Hospital",
):
    """
    Day/yesterday → real LabDayCollection_All (full reconciliation columns).
    Week → falls back to MODE totals (SP is single-day only).
    """
    p = (period or "today").lower().replace(" ", "_")
    use_sp = p in ("today", "yesterday", "day")

    if use_sp:
        from reports.day_collection_reconciliation import (
            get_day_collection_all_branches,
            _REPORT_LABELS,
        )
        bill_date = "yesterday" if p == "yesterday" else "today"
        result = get_day_collection_all_branches(
            bill_date, db_name, db_server, db_user, db_password
        )
        if "error" in result:
            return {"error": result["error"]}
        branches = result["branches"]
        if not branches:
            return {"error": f"No reconciliation data for {result['bill_date']}."}

        # Columns staff expect on the PDF (order preserved)
        col_keys = list(_REPORT_LABELS.keys())
        headers = ["Branch"] + [_REPORT_LABELS[k] for k in col_keys]

        wb = Workbook()
        ws = wb.active
        ws.title = "Day Collection"
        hr = _title_row(ws, hospital_name, len(headers))
        ws.cell(row=hr, column=1, value=f"Day Collection Reconciliation · {result['bill_date']}").font = Font(
            italic=True, name="Arial", size=10
        )
        hr += 1
        _style_header(ws, hr, headers)

        row_num = hr + 1
        sums = {k: 0.0 for k in col_keys}
        for b in sorted(branches, key=lambda x: (x.get("LOCATION") or "")):
            ws.cell(row=row_num, column=1, value=b.get("LOCATION") or "")
            for col_i, key in enumerate(col_keys, start=2):
                try:
                    val = float(b.get(key) or 0)
                except (TypeError, ValueError):
                    val = 0.0
                sums[key] += val
                c = ws.cell(row=row_num, column=col_i, value=val)
                c.number_format = "#,##0.00"
            row_num += 1

        # GRAND TOTAL row
        ws.cell(row=row_num, column=1, value="GRAND TOTAL").font = Font(bold=True, name="Arial")
        for col_i, key in enumerate(col_keys, start=2):
            c = ws.cell(row=row_num, column=col_i, value=sums[key])
            c.font = Font(bold=True, name="Arial")
            c.number_format = "#,##0.00"
        row_num += 2

        # Overall summary (same labels as PDF)
        ws.cell(row=row_num, column=1, value="OVERALL (ALL BRANCHES)").font = Font(bold=True, size=12, name="Arial")
        row_num += 1
        for key in col_keys:
            ws.cell(row=row_num, column=1, value=_REPORT_LABELS[key])
            c = ws.cell(row=row_num, column=2, value=sums[key])
            c.number_format = "#,##0.00"
            if key in ("GTOTALCREDITS", "TOTALCASHINHAND"):
                c.font = Font(bold=True, name="Arial")
            row_num += 1

        ws.column_dimensions["A"].width = 28
        for i in range(2, len(headers) + 1):
            ws.column_dimensions[get_column_letter(i)].width = 18

        safe = re.sub(r"[^A-Za-z0-9_]", "_", result["bill_date"])
        return _save(wb, f"day_collection_all_{safe}.xlsx", result["bill_date"])

    # Week / other multi periods: old MODE pivot (SP has no date range)
    return _export_multi_branch_mode_pivot(
        period, db_name, db_server, db_user, db_password, hospital_name
    )
def export_single_branch_collection(
    period,
    location_keyword,
    db_name,
    db_server=None,
    db_user=None,
    db_password=None,
    hospital_name="Hospital",
):
    if not location_keyword:
        return {"error": "Month/year export needs a branch. Example: export excel this month Uppal"}

    p = (period or "today").lower().replace(" ", "_")

    # ===== TODAY / YESTERDAY → real SP (LabDayCollection_All) =====
    if p in ("today", "yesterday", "day"):
        from reports.day_collection_reconciliation import (
            get_day_collection_one_branch,
            _REPORT_LABELS,
        )
        bill_date = "yesterday" if p == "yesterday" else "today"
        result = get_day_collection_one_branch(
            location_keyword, bill_date, db_name, db_server, db_user, db_password
        )
        if "error" in result:
            return {"error": result["error"]}
        b = result["branch"]

        wb = Workbook()
        ws = wb.active
        ws.title = "Branch Collection"
        hr = _title_row(ws, hospital_name, 2)
        _style_header(ws, hr, ["Metric", "Amount"])
        r = hr + 1
        ws.cell(row=r, column=1, value=f"Branch: {b.get('LOCATION')}")
        r += 1
        ws.cell(row=r, column=1, value=f"Date: {result['bill_date']}")
        r += 2
        for key, label in _REPORT_LABELS.items():
            try:
                val = float(b.get(key) or 0)
            except (TypeError, ValueError):
                val = 0.0
            ws.cell(row=r, column=1, value=label)
            c = ws.cell(row=r, column=2, value=val)
            c.number_format = "#,##0.00"
            if key in ("GTOTALCREDITS", "TOTALCASHINHAND"):
                c.font = Font(bold=True, name="Arial")
            r += 1
        ws.column_dimensions["A"].width = 48
        ws.column_dimensions["B"].width = 16
        safe = re.sub(r"[^A-Za-z0-9_]", "_", f"{b.get('LOCATION')}_{result['bill_date']}")
        return _save(wb, f"day_collection_{safe}.xlsx", result["bill_date"])

    # ===== MONTH / YEAR → MODE totals (SP is single-day only) =====
    date_from, date_to, label = _period_dates(period)
    conn = get_hospital_connection(db_name, db_server, db_user, db_password)
    if not conn:
        return {"error": "Could not connect to the hospital database."}
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT LOCATIONID, LOCATIONNAME FROM mstlocation WHERE LOCATIONNAME LIKE ? ORDER BY LOCATIONNAME",
            (f"%{location_keyword.strip()}%",),
        )
        locs = cur.fetchall()
        if not locs:
            conn.close()
            return {"error": f"No location matching '{location_keyword}'."}
        if len(locs) > 1:
            exact = [r for r in locs if (r[1] or "").lower() == location_keyword.strip().lower()]
            if len(exact) == 1:
                locs = exact
            else:
                conn.close()
                return {"error": "Multiple locations: " + ", ".join(r[1] for r in locs[:8])}
        loc_id, matched = locs[0][0], locs[0][1]

        cur.execute(
            "SELECT UPPER(LTRIM(RTRIM(MODE))) AS MODE, SUM(PAIDAMOUNT) AS Amt "
            "FROM trnmodeofcollectionsdet "
            "WHERE LOCATIONID = ? AND DATEOFBILL >= ? AND DATEOFBILL < ? "
            "GROUP BY UPPER(LTRIM(RTRIM(MODE)))",
            (loc_id, date_from, date_to),
        )
        rows = cur.fetchall()
    except Exception as e:
        conn.close()
        return {"error": f"Query failed: {e}"}
    conn.close()
    if not rows:
        return {"error": f"No collection for {matched} · {label}."}

    by_mode = {(m or "OTHER"): float(a or 0) for m, a in rows}

    def bucket(mode: str) -> str:
        m = (mode or "").upper()
        if "CASH" in m:
            return "CASH"
        if any(x in m for x in ("UPI", "ONLINE", "PHONEPE", "GPAY", "PAYTM")):
            return "UPI_ONLINE"
        if any(x in m for x in ("CARD", "CREDIT CARD", "DEBIT")):
            return "CARD"
        if any(x in m for x in ("CHEQUE", "CHECK", "DD")):
            return "CHEQUE"
        if "CREDIT" in m:
            return "CREDIT"
        return "OTHER"

    overall = {"CASH": 0.0, "CARD": 0.0, "UPI_ONLINE": 0.0, "CHEQUE": 0.0, "CREDIT": 0.0, "OTHER": 0.0}
    for mode, amt in by_mode.items():
        overall[bucket(mode)] += amt
    grand = sum(by_mode.values())

    wb = Workbook()
    ws = wb.active
    ws.title = "Branch Collection"
    headers = ["Metric", "Amount"]
    hr = _title_row(ws, hospital_name, 2)
    _style_header(ws, hr, headers)

    r = hr + 1
    ws.cell(row=r, column=1, value=f"Branch: {matched} ({loc_id})")
    r += 1
    ws.cell(row=r, column=1, value=f"Period: {label}")
    r += 2
    ws.cell(row=r, column=1, value="By payment mode").font = Font(bold=True)
    r += 1
    for mode in sorted(by_mode.keys()):
        ws.cell(row=r, column=1, value=mode)
        c = ws.cell(row=r, column=2, value=by_mode[mode])
        c.number_format = "#,##0.00"
        r += 1
    r += 1
    for label_s, val in [
        ("Total Cash", overall["CASH"]),
        ("Total Credit Card", overall["CARD"]),
        ("Total Cheque/Online/UPI Received", overall["UPI_ONLINE"] + overall["CHEQUE"]),
        ("Total UPI/Online", overall["UPI_ONLINE"]),
        ("Total Cheque", overall["CHEQUE"]),
        ("Credits", overall["CREDIT"]),
        ("Other", overall["OTHER"]),
        ("GRAND TOTAL (with all modes)", grand),
        ("Total Cash in Hand", overall["CASH"]),
        ("Total Online/UPI in Hand", overall["UPI_ONLINE"]),
        ("Core business cash collected", overall["CASH"]),
        ("Total cash received", overall["CASH"]),
    ]:
        ws.cell(row=r, column=1, value=label_s)
        c = ws.cell(row=r, column=2, value=val)
        c.number_format = "#,##0.00"
        if "GRAND" in label_s:
            c.font = Font(bold=True, name="Arial")
        r += 1
    ws.column_dimensions["A"].width = 48
    ws.column_dimensions["B"].width = 16
    safe = re.sub(r"[^A-Za-z0-9_]", "_", f"{matched}_{label}")
    return _save(wb, f"collection_{safe}_{date.today().isoformat()}.xlsx", label)
def export_top_tests(
    period, db_name, db_server=None, db_user=None, db_password=None, hospital_name="Hospital",
):
    date_from, date_to, label = _period_dates(period)
    conn = get_hospital_connection(db_name, db_server, db_user, db_password)
    if not conn:
        return {"error": "Could not connect to the hospital database."}
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT TOP 50 i.INVNAME, COUNT(*) AS Cnt "
            "FROM trninvlabdet d "
            "JOIN mstInvestigations i ON d.TCODE = i.INVCODE "
            "WHERE d.BILLDATE >= ? AND d.BILLDATE < ? "
            "GROUP BY i.INVNAME ORDER BY Cnt DESC",
            (date_from, date_to),
        )
        rows = cur.fetchall()
    except Exception as e:
        conn.close()
        return {"error": f"Query failed: {e}"}
    conn.close()
    if not rows:
        return {"error": f"No test data for {label}."}

    wb = Workbook()
    ws = wb.active
    ws.title = "Top Tests"
    headers = ["#", "Investigation", "Orders"]
    hr = _title_row(ws, hospital_name, 3)
    _style_header(ws, hr, headers)
    for i, (name, cnt) in enumerate(rows, start=1):
        ws.cell(row=hr + i, column=1, value=i)
        ws.cell(row=hr + i, column=2, value=name)
        ws.cell(row=hr + i, column=3, value=int(cnt or 0)).number_format = "#,##0"
    ws.column_dimensions["B"].width = 40
    safe = re.sub(r"[^A-Za-z0-9_]", "_", label)
    return _save(wb, f"top_tests_{safe}_{date.today().isoformat()}.xlsx", label)


def export_refunds_list(
    period, db_name, db_server=None, db_user=None, db_password=None, hospital_name="Hospital",
):
    date_from, date_to, label = _period_dates(period)
    conn = get_hospital_connection(db_name, db_server, db_user, db_password)
    if not conn:
        return {"error": "Could not connect to the hospital database."}
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT TOP 500 BILLNO, MODE, PAIDAMOUNT, DATEOFBILL, LOCATIONID "
            "FROM trnmodeofcollectionsdet "
            "WHERE TYPE = 'LabRefund' AND DATEOFBILL >= ? AND DATEOFBILL < ? "
            "ORDER BY DATEOFBILL DESC",
            (date_from, date_to),
        )
        rows = cur.fetchall()
    except Exception as e:
        conn.close()
        return {"error": f"Query failed: {e}"}
    conn.close()
    if not rows:
        return {"error": f"No refunds for {label}."}

    wb = Workbook()
    ws = wb.active
    ws.title = "Refunds"
    headers = ["Bill No", "Mode", "Amount", "Date", "LocationId"]
    hr = _title_row(ws, hospital_name, 5)
    _style_header(ws, hr, headers)
    for i, row in enumerate(rows):
        r = hr + 1 + i
        for col, val in enumerate(row, start=1):
            cell = ws.cell(row=r, column=col, value=val if col != 3 else float(val or 0))
            if col == 3:
                cell.number_format = "#,##0.00"
    safe = re.sub(r"[^A-Za-z0-9_]", "_", label)
    return _save(wb, f"refunds_{safe}_{date.today().isoformat()}.xlsx", label)


def export_registrations_by_branch(
    period, db_name, db_server=None, db_user=None, db_password=None, hospital_name="Hospital",
):
    date_from, date_to, label = _period_dates(period)
    conn = get_hospital_connection(db_name, db_server, db_user, db_password)
    if not conn:
        return {"error": "Could not connect to the hospital database."}
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT l.LOCATIONNAME, COUNT(*) AS Cnt "
            "FROM mstpatientregistration p "
            "JOIN mstlocation l ON p.LOCATIONID = l.LOCATIONID "
            "WHERE p.REGDATE >= ? AND p.REGDATE < ? "
            "GROUP BY l.LOCATIONNAME ORDER BY Cnt DESC",
            (date_from, date_to),
        )
        rows = cur.fetchall()
    except Exception as e:
        conn.close()
        return {"error": f"Query failed: {e}"}
    conn.close()
    if not rows:
        return {"error": f"No registrations for {label}."}

    wb = Workbook()
    ws = wb.active
    ws.title = "Registrations"
    headers = ["Branch", "Registrations"]
    hr = _title_row(ws, hospital_name, 2)
    _style_header(ws, hr, headers)
    for i, (name, cnt) in enumerate(rows):
        ws.cell(row=hr + 1 + i, column=1, value=name)
        ws.cell(row=hr + 1 + i, column=2, value=int(cnt or 0)).number_format = "#,##0"
    ws.column_dimensions["A"].width = 28
    safe = re.sub(r"[^A-Za-z0-9_]", "_", label)
    return _save(wb, f"registrations_{safe}_{date.today().isoformat()}.xlsx", label)
def run_excel_export(
    report_type: str,
    period: str,
    db_name: str,
    db_server=None,
    db_user=None,
    db_password=None,
    hospital_name: str = "Hospital",
    location_keyword: str = None,
) -> dict:
    key = (report_type or "collection").lower().strip()

    if key == "collection":
        # day/week → all branches + grand total
        # month/year → single branch only
        p = (period or "today").lower().replace(" ", "_")
        multi = p in (
            "today", "yesterday", "day",
            "this_week", "thisweek", "week",
            "last_week", "lastweek",
        )
        if multi:
            return export_all_branches_collection(
                period, db_name, db_server, db_user, db_password, hospital_name
            )
        return export_single_branch_collection(
            period, location_keyword, db_name, db_server, db_user, db_password, hospital_name
        )

    if key == "top_tests":
        return export_top_tests(period, db_name, db_server, db_user, db_password, hospital_name)
    if key == "refunds":
        return export_refunds_list(period, db_name, db_server, db_user, db_password, hospital_name)
    if key == "registrations":
        return export_registrations_by_branch(period, db_name, db_server, db_user, db_password, hospital_name)
    return {"error": "report_type must be: collection, top_tests, refunds, registrations"}

# backward-compatible alias
export_all_branches_collection = export_multi_branch_collection