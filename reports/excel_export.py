"""
Excel exports.
- day / week → multi-branch + GRAND TOTAL + overall mode totals
- month / year → single branch only (location required)
Row 1 = hospital/diagnostics name only.
"""

import re
import os
from datetime import date, timedelta
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter

from database.connection import get_hospital_connection
from agent.schema_ctx import get_profile, coll_amt


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

def export_all_branches_collection(
    period, db_name, db_server=None, db_user=None, db_password=None, hospital_name="Hospital",
):
    """
    today/yesterday → real LabDayCollection_All
    week → MODE pivot
    """
    p = (period or "today").lower().replace(" ", "_")

    if p in ("today", "yesterday", "day"):
        from reports.day_collection_readonly import get_day_collection_all_branches_readonly as get_day_collection_all_branches
        from reports.day_collection_reconciliation import _REPORT_LABELS
        bill_date = "yesterday" if p == "yesterday" else "today"
        result = get_day_collection_all_branches(
            bill_date, db_name, db_server, db_user, db_password
        )
        if "error" in result:
            return {"error": result["error"]}
        branches = result["branches"]
        if not branches:
            return {"error": f"No reconciliation data for {result['bill_date']}."}

        col_keys = list(_REPORT_LABELS.keys())
        headers = ["Branch"] + [_REPORT_LABELS[k] for k in col_keys]

        wb = Workbook()
        ws = wb.active
        ws.title = "Day Collection"
        hr = _title_row(ws, hospital_name, len(headers))
        ws.cell(row=hr, column=1, value=f"Day Collection · {result['bill_date']}").font = Font(
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

        ws.cell(row=row_num, column=1, value="GRAND TOTAL").font = Font(bold=True, name="Arial")
        for col_i, key in enumerate(col_keys, start=2):
            c = ws.cell(row=row_num, column=col_i, value=sums[key])
            c.font = Font(bold=True, name="Arial")
            c.number_format = "#,##0.00"
        row_num += 2

        ws.cell(row=row_num, column=1, value="OVERALL (ALL BRANCHES)").font = Font(
            bold=True, size=12, name="Arial"
        )
        row_num += 1
        for key in col_keys:
            ws.cell(row=row_num, column=1, value=_REPORT_LABELS[key])
            c = ws.cell(row=row_num, column=2, value=sums[key])
            c.number_format = "#,##0.00"
            row_num += 1

        ws.column_dimensions["A"].width = 28
        for i in range(2, len(headers) + 1):
            ws.column_dimensions[get_column_letter(i)].width = 18

        safe = re.sub(r"[^A-Za-z0-9_]", "_", result["bill_date"])
        return _save(wb, f"day_collection_all_{safe}.xlsx", result["bill_date"])

    # week etc.
    return _export_multi_branch_mode_pivot(
        period, db_name, db_server, db_user, db_password, hospital_name
    )
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
    # Week / other multi-day periods: real MODE pivot across branches
    # (the stored procedure is single-day only, so this can't reuse it)
    date_from, date_to, label = _period_dates(period)
    conn = get_hospital_connection(db_name, db_server, db_user, db_password)
    if not conn:
        return {"error": "Could not connect to the hospital database."}
    try:
        cur = conn.cursor()
        cur.execute(
            f"SELECT l.LOCATIONNAME, UPPER(LTRIM(RTRIM(m.MODE))) AS MODE, SUM({coll_amt(get_profile(conn, db_name, db_server), 'm')}) AS Amt "
            "FROM trnmodeofcollectionsdet m "
            "JOIN mstlocation l ON m.LOCATIONID = l.LOCATIONID "
            "WHERE m.DATEOFBILL >= ? AND m.DATEOFBILL < ? "
            "GROUP BY l.LOCATIONNAME, UPPER(LTRIM(RTRIM(m.MODE))) "
            "ORDER BY l.LOCATIONNAME",
            (date_from, date_to),
        )
        rows = cur.fetchall()
    except Exception as e:
        conn.close()
        return {"error": f"Query failed: {e}"}
    conn.close()
    if not rows:
        return {"error": f"No collection data for {label}."}

    branches = {}
    all_modes = set()
    for branch, mode, amt in rows:
        branches.setdefault(branch, {})[mode] = float(amt or 0)
        all_modes.add(mode)
    all_modes = sorted(all_modes)

    wb = Workbook()
    ws = wb.active
    ws.title = "Collection"
    headers = ["Branch"] + all_modes + ["Total"]
    hr = _title_row(ws, hospital_name, len(headers))
    ws.cell(row=hr, column=1, value=f"Collection by Mode · {label}").font = Font(italic=True, name="Arial", size=10)
    hr += 1
    _style_header(ws, hr, headers)

    row_num = hr + 1
    mode_sums = {m: 0.0 for m in all_modes}
    for branch in sorted(branches.keys()):
        ws.cell(row=row_num, column=1, value=branch)
        row_total = 0.0
        for col_i, mode in enumerate(all_modes, start=2):
            amt = branches[branch].get(mode, 0.0)
            mode_sums[mode] += amt
            row_total += amt
            c = ws.cell(row=row_num, column=col_i, value=amt)
            c.number_format = "#,##0.00"
        total_col = len(all_modes) + 2
        c = ws.cell(row=row_num, column=total_col, value=row_total)
        c.font = Font(bold=True, name="Arial")
        c.number_format = "#,##0.00"
        row_num += 1

    ws.cell(row=row_num, column=1, value="GRAND TOTAL").font = Font(bold=True, name="Arial")
    grand_total = 0.0
    for col_i, mode in enumerate(all_modes, start=2):
        c = ws.cell(row=row_num, column=col_i, value=mode_sums[mode])
        c.font = Font(bold=True, name="Arial")
        c.number_format = "#,##0.00"
        grand_total += mode_sums[mode]
    c = ws.cell(row=row_num, column=len(all_modes) + 2, value=grand_total)
    c.font = Font(bold=True, name="Arial")
    c.number_format = "#,##0.00"

    ws.column_dimensions["A"].width = 28
    for i in range(2, len(headers) + 1):
        ws.column_dimensions[get_column_letter(i)].width = 16

    safe = re.sub(r"[^A-Za-z0-9_]", "_", label)
    return _save(wb, f"collection_by_mode_{safe}_{date.today().isoformat()}.xlsx", label)
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
            f"SELECT UPPER(LTRIM(RTRIM(MODE))) AS MODE, SUM({coll_amt(get_profile(conn, db_name, db_server))}) AS Amt "
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
            f"SELECT TOP 500 BILLNO, MODE, {coll_amt(get_profile(conn, db_name, db_server))}, DATEOFBILL, LOCATIONID "
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
def _export_centromed_detailed_collection(period, db_name, db_server,
                                          db_user, db_password, hospital_name,
                                          location_keyword):
    """Recorded-value collections for clients whose PAIDAMOUNT is not used (profile = 'total')."""
    from collections import defaultdict
    from decimal import Decimal
    from reports.collection_compat import collection_detailed_data
    from datetime import datetime

    start, end, label = _period_dates(period)
    data = collection_detailed_data(start, end, db_name, db_server,
                                    db_user, db_password, location_keyword)
    if "error" in data:
        return data

    MONEY = '#,##0.00;[Red](#,##0.00);-'
    rows = data["rows"]
    last_day = (date.fromisoformat(end) - timedelta(days=1)).isoformat()
    span = start if start == last_day else f"{start} to {last_day}"
    scope = f" · {location_keyword.title()}" if location_keyword else ""

    clean = []
    matrix = defaultdict(lambda: defaultdict(Decimal))     # branch -> mode -> amount
    by_branch = defaultdict(lambda: [0, Decimal(0), Decimal(0), Decimal(0)])
    by_mode = defaultdict(lambda: [0, Decimal(0), Decimal(0), Decimal(0)])
    by_day = defaultdict(lambda: [0, Decimal(0), Decimal(0), Decimal(0)])
    fallback_count = 0
    for dt, branch, bill, uhid, patient, mode, paid, total, _chosen, _src in rows:
        paid, total = Decimal(str(paid or 0)), Decimal(str(total or 0))
        chosen = paid if paid != 0 else total
        source = "PAIDAMOUNT" if paid != 0 else ("TOTALAMOUNT (fallback)" if total != 0 else "ZERO")
        fallback_count += source == "TOTALAMOUNT (fallback)"
        branch = str(branch or "Unknown").strip()
        mode = str(mode or "Unknown").strip().title()          # CASH / Cash -> Cash
        clean.append((dt, branch, bill, uhid, patient, mode, paid, total, chosen, source))
        matrix[branch][mode] += chosen
        for key, bucket in ((branch, by_branch), (mode, by_mode), (str(dt)[:10], by_day)):
            v = bucket[key]
            v[0] += 1; v[1] += paid; v[2] += total; v[3] += chosen
    grand = sum((v[3] for v in by_branch.values()), Decimal(0))
    modes = sorted(by_mode)

    wb = Workbook()
    ov = wb.active
    ov.title = "Overview"
    _title_row(ov, hospital_name, max(len(modes) + 2, 4))
    ov.cell(2, 1, f"Collections · {label}{scope} · {span}").font = Font(italic=True, name="Arial", size=10)
    kpis = [("Total collection", float(grand)), ("Bills / records", len(clean)),
            ("Average per bill", float(grand / len(clean)) if clean else 0)]
    for i, (k, v) in enumerate(kpis, 4):
        ov.cell(i, 1, k).font = Font(bold=True, name="Arial")
        c = ov.cell(i, 2, v)
        c.font = Font(bold=True, size=12, name="Arial")
        c.number_format = '#,##0' if k.startswith("Bills") else '#,##0.00'
    r0 = 8
    ov.cell(r0 - 1, 1, "By branch and payment mode").font = Font(bold=True, size=12, name="Arial")
    _style_header(ov, r0, ["Branch"] + modes + ["Total"])
    r = r0 + 1
    col_tot = {m: Decimal(0) for m in modes}
    for br in sorted(matrix):
        ov.cell(r, 1, br)
        rt = Decimal(0)
        for j, m in enumerate(modes, 2):
            v = matrix[br].get(m, Decimal(0)); rt += v; col_tot[m] += v
            ov.cell(r, j, float(v)).number_format = MONEY
        c = ov.cell(r, len(modes) + 2, float(rt)); c.font = Font(bold=True, name="Arial"); c.number_format = MONEY
        r += 1
    ov.cell(r, 1, "GRAND TOTAL").font = Font(bold=True, name="Arial")
    for j, m in enumerate(modes, 2):
        c = ov.cell(r, j, float(col_tot[m])); c.font = Font(bold=True, name="Arial"); c.number_format = MONEY
    c = ov.cell(r, len(modes) + 2, float(grand)); c.font = Font(bold=True, name="Arial"); c.number_format = MONEY
    ov.column_dimensions["A"].width = 30
    for j in range(2, len(modes) + 3):
        ov.column_dimensions[get_column_letter(j)].width = 18
    ov.sheet_view.showGridLines = False
    if fallback_count:
        ov.cell(r + 2, 1, "Amounts are the recorded bill value (this system does not fill PAID AMOUNT). "
                          "Confirm against finance records before using as cash received.").font = Font(
                              italic=True, color="B45309", name="Arial", size=9)

    def make_summary(title, first_col, grouped):
        ws = wb.create_sheet(title)
        _title_row(ws, hospital_name, 5)
        _style_header(ws, 3, [first_col, "Bills", "Amount"])
        n = 4
        for key, v in sorted(grouped.items()):
            ws.cell(n, 1, key); ws.cell(n, 2, v[0]).number_format = '#,##0'
            ws.cell(n, 3, float(v[3])).number_format = MONEY
            n += 1
        ws.cell(n, 1, "GRAND TOTAL").font = Font(bold=True, name="Arial")
        ws.cell(n, 2, sum(v[0] for v in grouped.values())).number_format = '#,##0'
        c = ws.cell(n, 3, float(sum((v[3] for v in grouped.values()), Decimal(0))))
        c.number_format = MONEY; c.font = Font(bold=True, name="Arial")
        for col, w in zip("ABC", (30, 12, 20)):
            ws.column_dimensions[col].width = w
        ws.freeze_panes = "A4"; ws.sheet_view.showGridLines = False

    make_summary("Branch Summary", "Branch", by_branch)
    make_summary("Mode Summary", "Payment Mode", by_mode)
    if len(by_day) > 1:
        make_summary("Daily Summary", "Date", by_day)

    detail = wb.create_sheet("Transactions")
    columns = ["Date", "Branch", "Bill No.", "UHID", "Patient", "Payment Mode", "Amount"]
    hr = _title_row(detail, hospital_name, len(columns))
    _style_header(detail, hr + 1, columns)
    for i, rec in enumerate(clean, hr + 2):
        dt, branch, bill, uhid, patient, mode, _p, _t, chosen, _s = rec
        for c, value in enumerate([dt, branch, bill, uhid, patient, mode, float(chosen)], 1):
            cell = detail.cell(i, c, value)
            if c == 7:
                cell.number_format = MONEY
            if c == 1 and isinstance(dt, (datetime, date)):
                cell.number_format = 'dd mmm yyyy hh:mm'
    last = hr + 1 + len(clean)
    detail.cell(last + 1, 1, "GRAND TOTAL").font = Font(bold=True, name="Arial")
    c = detail.cell(last + 1, 7, float(grand)); c.number_format = MONEY; c.font = Font(bold=True, name="Arial")
    detail.freeze_panes = f"A{hr + 2}"
    detail.auto_filter.ref = f"A{hr + 1}:G{max(last, hr + 2)}"
    for idx, width in enumerate((22, 24, 18, 18, 28, 16, 16), 1):
        detail.column_dimensions[get_column_letter(idx)].width = width
    detail.sheet_view.showGridLines = False

    notes = wb.create_sheet("Notes")
    for row in (["Period", f"{label} ({span})"], ["Records", len(clean)],
                ["Records using bill value (TOTALAMOUNT)", fallback_count],
                ["Amount", "PAIDAMOUNT where filled, otherwise TOTALAMOUNT (per record)"],
                ["WARNING", data["warning"]]):
        notes.append(row)
    notes.column_dimensions["A"].width = 40; notes.column_dimensions["B"].width = 100
    safe = re.sub(r"[^A-Za-z0-9_]", "_", label)
    return _save(wb, f"collection_{safe}_{date.today().isoformat()}.xlsx", label)


def _is_centromed_export(db_name, hospital_name, db_server=None, db_user=None, db_password=None):
    """Use the detailed 'paid, else total' exporter for any client whose profile says
    collections are recorded in TOTALAMOUNT (auto-detected per database, no client list).
    CENTROMED_EXCEL_FALLBACK_DATABASES force-enables; COLLECTION_METRIC_OVERRIDE can force either way."""
    forced = {v.strip().casefold() for v in
              os.environ.get("CENTROMED_EXCEL_FALLBACK_DATABASES", "").split(",") if v.strip()}
    if (db_name or "").strip().casefold() in forced:
        return True
    try:
        from agent.schema_ctx import get_profile
        conn = get_hospital_connection(db_name, db_server, db_user, db_password)
        if not conn:
            return False
        try:
            return get_profile(conn, db_name, db_server)["coll_metric"] == "total"
        finally:
            conn.close()
    except Exception:
        return False


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
        # Which exporter runs is decided per database from how PAIDAMOUNT is filled
        # (row evidence over 90 days, see agent.schema_ctx). Env settings
        # CENTROMED_EXCEL_FALLBACK_DATABASES / COLLECTION_METRIC_OVERRIDE can force it.
        # Databases that fill PAIDAMOUNT keep the original exporter unchanged.
        if _is_centromed_export(db_name, hospital_name, db_server, db_user, db_password):
            return _export_centromed_detailed_collection(
                period, db_name, db_server, db_user, db_password,
                hospital_name, location_keyword,
            )
        p = (period or "today").lower().replace(" ", "_")
        multi = p in (
            "today", "yesterday", "day",
            "this_week", "thisweek", "week",
            "last_week", "lastweek",
        )
        # location given → always single branch
        if location_keyword:
            return export_single_branch_collection(
                period, location_keyword, db_name, db_server, db_user, db_password, hospital_name
            )
        # no location + day/week → all branches
        if multi:
            return export_all_branches_collection(
                period, db_name, db_server, db_user, db_password, hospital_name
            )
        # month/year without location
        return {"error": "Month/year export needs a branch. Example: export excel this month Uppal"}
    if key == "top_tests":
        return export_top_tests(period, db_name, db_server, db_user, db_password, hospital_name)
    if key == "refunds":
        return export_refunds_list(period, db_name, db_server, db_user, db_password, hospital_name)
    if key == "registrations":
        return export_registrations_by_branch(period, db_name, db_server, db_user, db_password, hospital_name)
    return {"error": "report_type must be: collection, top_tests, refunds, registrations"}

