"""
Excel exports.
- day / this_week → multi-branch collection + grand totals (all modes)
- this_month / last_month / this_year → single-branch only (pass location_keyword)
Row 1 = hospital/diagnostics name only. Headers from row 2.
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
    # today / day
    return today.isoformat(), (today + timedelta(days=1)).isoformat(), "Today"


def _is_multi_branch(period: str) -> bool:
    p = (period or "today").lower().replace(" ", "_")
    return p in ("today", "yesterday", "this_week", "thisweek", "week", "last_week", "lastweek", "day")


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


def _mode_bucket(mode: str) -> str:
    m = (mode or "").upper().strip()
    if "CASH" in m:
        return "CASH"
    if "UPI" in m or "ONLINE" in m or "PHONEPE" in m or "GPAY" in m or "PAYTM" in m:
        return "UPI_ONLINE"
    if "CARD" in m or "CREDIT" in m or "DEBIT" in m:
        return "CARD"
    if "CHEQUE" in m or "CHECK" in m or "DD" in m:
        return "CHEQUE"
    if "CREDIT" in m:  # company credit etc
        return "CREDIT"
    return "OTHER"


def _resolve_location(conn, keyword: str):
    if not keyword:
        return None, None
    kw = keyword.strip()
    cur = conn.cursor()
    cur.execute(
        "SELECT LOCATIONID, LOCATIONNAME FROM mstlocation "
        "WHERE LOCATIONNAME LIKE ? ORDER BY LOCATIONNAME",
        (f"%{kw}%",),
    )
    rows = cur.fetchall()
    if not rows:
        return None, None
    if len(rows) > 1:
        exact = [r for r in rows if (r[1] or "").lower() == kw.lower()]
        if len(exact) == 1:
            return exact[0][0], exact[0][1]
        return "AMBIGUOUS", [r[1] for r in rows[:8]]
    return rows[0][0], rows[0][1]


def export_multi_branch_collection(
    period, db_name, db_server=None, db_user=None, db_password=None, hospital_name="Hospital",
):
    date_from, date_to, label = _period_dates(period)
    conn = get_hospital_connection(db_name, db_server, db_user, db_password)
    if not conn:
        return {"error": "Could not connect to the hospital database."}
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT l.LOCATIONNAME, UPPER(LTRIM(RTRIM(m.MODE))) AS MODE, SUM(m.PAIDAMOUNT) AS Amt "
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
        branches.setdefault(branch or "Unknown", {})[mode or "OTHER"] = float(amt or 0)
        all_modes.add(mode or "OTHER")
    all_modes = sorted(all_modes)

    # Bucket totals across ALL branches
    overall = {"CASH": 0.0, "CARD": 0.0, "UPI_ONLINE": 0.0, "CHEQUE": 0.0, "CREDIT": 0.0, "OTHER": 0.0}
    for modes in branches.values():
        for mode, amt in modes.items():
            overall[_mode_bucket(mode)] += amt
    grand = sum(overall.values())

    wb = Workbook()
    ws = wb.active
    ws.title = "All Branches"

    headers = ["Branch"] + all_modes + ["Total"]
    header_row = _title_row(ws, hospital_name, len(headers))
    _style_header(ws, header_row, headers)

    row_num = header_row + 1
    first_data = row_num
    for branch in sorted(branches.keys()):
        ws.cell(row=row_num, column=1, value=branch).font = Font(name="Arial")
        for col, mode in enumerate(all_modes, start=2):
            c = ws.cell(row=row_num, column=col, value=branches[branch].get(mode, 0.0))
            c.font = Font(name="Arial")
            c.number_format = "#,##0.00"
        total_col = len(all_modes) + 2
        fl, ll = get_column_letter(2), get_column_letter(total_col - 1)
        tc = ws.cell(row=row_num, column=total_col, value=f"=SUM({fl}{row_num}:{ll}{row_num})")
        tc.font = Font(name="Arial", bold=True)
        tc.number_format = "#,##0.00"
        row_num += 1
    last_data = row_num - 1

    # GRAND TOTAL row (all branches)
    ws.cell(row=row_num, column=1, value="GRAND TOTAL").font = Font(bold=True, name="Arial")
    for col in range(2, len(all_modes) + 3):
        cl = get_column_letter(col)
        c = ws.cell(row=row_num, column=col, value=f"=SUM({cl}{first_data}:{cl}{last_data})")
        c.font = Font(bold=True, name="Arial")
        c.number_format = "#,##0.00"
    row_num += 2

    # Overall summary block (all branches combined)
    ws.cell(row=row_num, column=1, value="OVERALL (ALL BRANCHES)").font = Font(bold=True, size=12, name="Arial")
    row_num += 1
    summary = [
        ("Total Cash", overall["CASH"]),
        ("Total Credit Card", overall["CARD"]),
        ("Total Cheque/Online/UPI Received", overall["UPI_ONLINE"] + overall["CHEQUE"]),
        ("Total UPI/Online", overall["UPI_ONLINE"]),
        ("Total Cheque", overall["CHEQUE"]),
        ("Total Credit (other)", overall["CREDIT"]),
        ("Other", overall["OTHER"]),
        ("GRAND TOTAL (all modes, all branches)", grand),
        ("Total Cash in Hand (Cash)", overall["CASH"]),
        ("Total Online/UPI in Hand", overall["UPI_ONLINE"]),
    ]
    for label_s, val in summary:
        ws.cell(row=row_num, column=1, value=label_s).font = Font(name="Arial")
        c = ws.cell(row=row_num, column=2, value=val)
        c.number_format = "#,##0.00"
        c.font = Font(name="Arial", bold=("GRAND" in label_s))
        row_num += 1

    ws.column_dimensions["A"].width = 42
    for col in range(2, len(all_modes) + 3):
        ws.column_dimensions[get_column_letter(col)].width = 14

    safe = re.sub(r"[^A-Za-z0-9_]", "_", label)
    return _save(wb, f"collection_all_branches_{safe}_{date.today().isoformat()}.xlsx", label)


def export_single_branch_collection(
    period, location_keyword, db_name, db_server=None, db_user=None, db_password=None, hospital_name="Hospital",
):
    if not location_keyword:
        return {"error": "Month/year export needs a branch name. Example: export excel this month Uppal"}

    date_from, date_to, label = _period_dates(period)
    conn = get_hospital_connection(db_name, db_server, db_user, db_password)
    if not conn:
        return {"error": "Could not connect to the hospital database."}
    try:
        loc_id, matched = _resolve_location(conn, location_keyword)
        if loc_id is None:
            conn.close()
            return {"error": f"No location matching '{location_keyword}'."}
        if loc_id == "AMBIGUOUS":
            conn.close()
            return {"error": f"Multiple locations match '{location_keyword}': {', '.join(matched)}"}

        cur = conn.cursor()
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

    by_mode = { (m or "OTHER"): float(a or 0) for m, a in rows }
    overall = {"CASH": 0.0, "CARD": 0.0, "UPI_ONLINE": 0.0, "CHEQUE": 0.0, "CREDIT": 0.0, "OTHER": 0.0}
    for mode, amt in by_mode.items():
        overall[_mode_bucket(mode)] += amt
    grand = sum(by_mode.values())

    wb = Workbook()
    ws = wb.active
    ws.title = "Branch Collection"
    headers = ["Metric", "Amount"]
    header_row = _title_row(ws, hospital_name, 2)
    _style_header(ws, header_row, headers)

    r = header_row + 1
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
    summary = [
        ("Total Cash", overall["CASH"]),
        ("Total Credit Card", overall["CARD"]),
        ("Total Cheque/Online/UPI Received", overall["UPI_ONLINE"] + overall["CHEQUE"]),
        ("Total UPI/Online", overall["UPI_ONLINE"]),
        ("Total Cheque", overall["CHEQUE"]),
        ("Credits / Other credit", overall["CREDIT"]),
        ("Other", overall["OTHER"]),
        ("GRAND TOTAL (with all modes)", grand),
        ("Total Cash in Hand", overall["CASH"]),
        ("Total Online/UPI in Hand", overall["UPI_ONLINE"]),
        ("Core business cash collected (Cash)", overall["CASH"]),
        ("Total cash received", overall["CASH"]),
    ]
    for label_s, val in summary:
        ws.cell(row=r, column=1, value=label_s).font = Font(name="Arial", bold=("GRAND" in label_s))
        c = ws.cell(row=r, column=2, value=val)
        c.number_format = "#,##0.00"
        c.font = Font(name="Arial", bold=("GRAND" in label_s))
        r += 1

    ws.column_dimensions["A"].width = 48
    ws.column_dimensions["B"].width = 16
    safe = re.sub(r"[^A-Za-z0-9_]", "_", f"{matched}_{label}")
    return _save(wb, f"collection_{safe}_{date.today().isoformat()}.xlsx", label)


def export_top_tests(period, db_name, db_server=None, db_user=None, db_password=None, hospital_name="Hospital", location_keyword=None):
    date_from, date_to, label = _period_dates(period)
    conn = get_hospital_connection(db_name, db_server, db_user, db_password)
    if not conn:
        return {"error": "Could not connect to the hospital database."}
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT TOP 50 i.INVNAME, COUNT(*) AS Cnt FROM trninvlabdet d "
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


def export_refunds_list(period, db_name, db_server=None, db_user=None, db_password=None, hospital_name="Hospital", location_keyword=None):
    date_from, date_to, label = _period_dates(period)
    conn = get_hospital_connection(db_name, db_server, db_user, db_password)
    if not conn:
        return {"error": "Could not connect to the hospital database."}
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT TOP 500 BILLNO, MODE, PAIDAMOUNT, DATEOFBILL, LOCATIONID "
            "FROM trnmodeofcollectionsdet WHERE TYPE = 'LabRefund' "
            "AND DATEOFBILL >= ? AND DATEOFBILL < ? ORDER BY DATEOFBILL DESC",
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
            c = ws.cell(row=r, column=col, value=float(val) if col == 3 and val is not None else (str(val) if val is not None else ""))
            if col == 3:
                c.number_format = "#,##0.00"
    safe = re.sub(r"[^A-Za-z0-9_]", "_", label)
    return _save(wb, f"refunds_{safe}_{date.today().isoformat()}.xlsx", label)


def export_registrations_by_branch(period, db_name, db_server=None, db_user=None, db_password=None, hospital_name="Hospital", location_keyword=None):
    date_from, date_to, label = _period_dates(period)
    conn = get_hospital_connection(db_name, db_server, db_user, db_password)
    if not conn:
        return {"error": "Could not connect to the hospital database."}
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT l.LOCATIONNAME, COUNT(*) AS Cnt FROM mstpatientregistration p "
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
        if _is_multi_branch(period):
            return export_multi_branch_collection(
                period, db_name, db_server, db_user, db_password, hospital_name
            )
        return export_single_branch_collection(
            period, location_keyword, db_name, db_server, db_user, db_password, hospital_name
        )
    if key == "top_tests":
        return export_top_tests(period, db_name, db_server, db_user, db_password, hospital_name, location_keyword)
    if key == "refunds":
        return export_refunds_list(period, db_name, db_server, db_user, db_password, hospital_name, location_keyword)
    if key == "registrations":
        return export_registrations_by_branch(period, db_name, db_server, db_user, db_password, hospital_name, location_keyword)
    return {"error": "report_type must be: collection, top_tests, refunds, registrations"}