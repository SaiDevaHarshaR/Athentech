"""
Excel exports (in-memory BytesIO).
Row 1 = institution name. Column headers start at row 2.
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
    if p in ("yesterday",):
        d = today - timedelta(days=1)
        return d.isoformat(), (d + timedelta(days=1)).isoformat(), "Yesterday"
    if p in ("this_month", "thismonth"):
        start = today.replace(day=1)
        return start.isoformat(), (today + timedelta(days=1)).isoformat(), "This Month"
    if p in ("last_month", "lastmonth"):
        first_this = today.replace(day=1)
        last_month_start = (first_this - timedelta(days=1)).replace(day=1)
        return last_month_start.isoformat(), first_this.isoformat(), "Last Month"
    if p in ("this_week", "thisweek"):
        start = today - timedelta(days=today.weekday())
        return start.isoformat(), (today + timedelta(days=1)).isoformat(), "This Week"
    return today.isoformat(), (today + timedelta(days=1)).isoformat(), "Today"


def _title_row(ws, hospital_name: str, subtitle: str, col_span: int):
    """Row 1: hospital name only (as requested). Subtitle goes in row 2 as a note, headers at row 3 if needed.
    User asked: first row only show hospital name — so title = name, headers start row 2.
    """
    name = (hospital_name or "Hospital").strip() or "Hospital"
    cell = ws.cell(row=1, column=1, value=name)
    cell.font = Font(bold=True, size=14, name="Arial", color="1F4E79")
    if col_span > 1:
        ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=col_span)
    # optional thin subtitle under name is NOT used — only name on row 1
    return 2  # next free row for column headers


def _style_header_row(ws, row: int, headers: list):
    header_font = Font(bold=True, color="FFFFFF", name="Arial")
    header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
    for col, h in enumerate(headers, start=1):
        cell = ws.cell(row=row, column=col, value=h)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center")


def _save(wb, filename: str, period_label: str) -> dict:
    bio = BytesIO()
    wb.save(bio)
    bio.seek(0)
    return {"file": bio, "filename": filename, "period_label": period_label}


def export_all_branches_collection(
    period: str,
    db_name: str,
    db_server=None,
    db_user=None,
    db_password=None,
    hospital_name: str = "Hospital",
) -> dict:
    date_from, date_to, label = _period_dates(period)
    conn = get_hospital_connection(db_name, db_server, db_user, db_password)
    if not conn:
        return {"error": "Could not connect to the hospital database."}
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT l.LOCATIONNAME, UPPER(LTRIM(RTRIM(m.MODE))) AS MODE, SUM(m.PAIDAMOUNT) AS Amt "
            "FROM trnmodeofcollectionsdet m "
            "JOIN mstlocation l ON m.LOCATIONID = l.LOCATIONID "
            "WHERE m.DATEOFBILL >= ? AND m.DATEOFBILL < ? "
            "GROUP BY l.LOCATIONNAME, UPPER(LTRIM(RTRIM(m.MODE))) "
            "ORDER BY l.LOCATIONNAME",
            (date_from, date_to),
        )
        rows = cursor.fetchall()
    except Exception as e:
        conn.close()
        return {"error": f"Query failed: {e}"}
    conn.close()

    if not rows:
        return {"error": f"No collection data found for {label}."}

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
    header_row = _title_row(ws, hospital_name, label, len(headers))
    _style_header_row(ws, header_row, headers)

    row_num = header_row + 1
    for branch in sorted(branches.keys()):
        ws.cell(row=row_num, column=1, value=branch).font = Font(name="Arial")
        for col, mode in enumerate(all_modes, start=2):
            amt = branches[branch].get(mode, 0.0)
            c = ws.cell(row=row_num, column=col, value=amt)
            c.font = Font(name="Arial")
            c.number_format = "#,##0"
        total_col = len(all_modes) + 2
        first_mode_col = get_column_letter(2)
        last_mode_col = get_column_letter(total_col - 1)
        tc = ws.cell(
            row=row_num,
            column=total_col,
            value=f"=SUM({first_mode_col}{row_num}:{last_mode_col}{row_num})",
        )
        tc.font = Font(name="Arial", bold=True)
        tc.number_format = "#,##0"
        row_num += 1

    total_row = row_num
    ws.cell(row=total_row, column=1, value="GRAND TOTAL").font = Font(bold=True, name="Arial")
    for col in range(2, len(all_modes) + 3):
        col_letter = get_column_letter(col)
        first_data = header_row + 1
        last_data = total_row - 1
        c = ws.cell(
            row=total_row,
            column=col,
            value=f"=SUM({col_letter}{first_data}:{col_letter}{last_data})",
        )
        c.font = Font(bold=True, name="Arial")
        c.number_format = "#,##0"

    ws.column_dimensions["A"].width = 28
    for col in range(2, len(all_modes) + 3):
        ws.column_dimensions[get_column_letter(col)].width = 14

    safe = re.sub(r"[^A-Za-z0-9_]", "_", label)
    return _save(wb, f"collection_{safe}_{date.today().isoformat()}.xlsx", label)


def export_top_tests(
    period: str,
    db_name: str,
    db_server=None,
    db_user=None,
    db_password=None,
    hospital_name: str = "Hospital",
) -> dict:
    date_from, date_to, label = _period_dates(period)
    conn = get_hospital_connection(db_name, db_server, db_user, db_password)
    if not conn:
        return {"error": "Could not connect to the hospital database."}
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT TOP 50 i.INVNAME, COUNT(*) AS Cnt "
            "FROM trninvlabdet d "
            "JOIN mstInvestigations i ON d.TCODE = i.INVCODE "
            "WHERE d.BILLDATE >= ? AND d.BILLDATE < ? "
            "GROUP BY i.INVNAME ORDER BY Cnt DESC",
            (date_from, date_to),
        )
        rows = cursor.fetchall()
    except Exception as e:
        conn.close()
        return {"error": f"Query failed: {e}"}
    conn.close()
    if not rows:
        return {"error": f"No test volume data for {label}."}

    wb = Workbook()
    ws = wb.active
    ws.title = "Top Tests"
    headers = ["#", "Investigation", "Orders"]
    header_row = _title_row(ws, hospital_name, label, len(headers))
    _style_header_row(ws, header_row, headers)
    for i, (name, cnt) in enumerate(rows, start=1):
        r = header_row + i
        ws.cell(row=r, column=1, value=i)
        ws.cell(row=r, column=2, value=name)
        ws.cell(row=r, column=3, value=int(cnt or 0)).number_format = "#,##0"
    ws.column_dimensions["A"].width = 6
    ws.column_dimensions["B"].width = 40
    ws.column_dimensions["C"].width = 12
    safe = re.sub(r"[^A-Za-z0-9_]", "_", label)
    return _save(wb, f"top_tests_{safe}_{date.today().isoformat()}.xlsx", label)


def export_refunds_list(
    period: str,
    db_name: str,
    db_server=None,
    db_user=None,
    db_password=None,
    hospital_name: str = "Hospital",
) -> dict:
    date_from, date_to, label = _period_dates(period)
    conn = get_hospital_connection(db_name, db_server, db_user, db_password)
    if not conn:
        return {"error": "Could not connect to the hospital database."}
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT TOP 500 BILLNO, MODE, PAIDAMOUNT, DATEOFBILL, LOCATIONID "
            "FROM trnmodeofcollectionsdet "
            "WHERE TYPE = 'LabRefund' AND DATEOFBILL >= ? AND DATEOFBILL < ? "
            "ORDER BY DATEOFBILL DESC",
            (date_from, date_to),
        )
        rows = cursor.fetchall()
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
    header_row = _title_row(ws, hospital_name, label, len(headers))
    _style_header_row(ws, header_row, headers)
    for i, (bill, mode, amt, dt, loc) in enumerate(rows):
        r = header_row + 1 + i
        ws.cell(row=r, column=1, value=bill)
        ws.cell(row=r, column=2, value=mode)
        c = ws.cell(row=r, column=3, value=float(amt or 0))
        c.number_format = "#,##0.00"
        ws.cell(row=r, column=4, value=str(dt) if dt else "")
        ws.cell(row=r, column=5, value=loc)
    for col, w in enumerate([16, 12, 12, 20, 12], start=1):
        ws.column_dimensions[get_column_letter(col)].width = w
    safe = re.sub(r"[^A-Za-z0-9_]", "_", label)
    return _save(wb, f"refunds_{safe}_{date.today().isoformat()}.xlsx", label)


def export_registrations_by_branch(
    period: str,
    db_name: str,
    db_server=None,
    db_user=None,
    db_password=None,
    hospital_name: str = "Hospital",
) -> dict:
    date_from, date_to, label = _period_dates(period)
    conn = get_hospital_connection(db_name, db_server, db_user, db_password)
    if not conn:
        return {"error": "Could not connect to the hospital database."}
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT l.LOCATIONNAME, COUNT(*) AS Cnt "
            "FROM mstpatientregistration p "
            "JOIN mstlocation l ON p.LOCATIONID = l.LOCATIONID "
            "WHERE p.REGDATE >= ? AND p.REGDATE < ? "
            "GROUP BY l.LOCATIONNAME ORDER BY Cnt DESC",
            (date_from, date_to),
        )
        rows = cursor.fetchall()
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
    header_row = _title_row(ws, hospital_name, label, len(headers))
    _style_header_row(ws, header_row, headers)
    for i, (name, cnt) in enumerate(rows):
        r = header_row + 1 + i
        ws.cell(row=r, column=1, value=name)
        ws.cell(row=r, column=2, value=int(cnt or 0)).number_format = "#,##0"
    ws.column_dimensions["A"].width = 28
    ws.column_dimensions["B"].width = 14
    safe = re.sub(r"[^A-Za-z0-9_]", "_", label)
    return _save(wb, f"registrations_{safe}_{date.today().isoformat()}.xlsx", label)


# Dispatcher used by /generate-excel
_EXPORTERS = {
    "collection": export_all_branches_collection,
    "top_tests": export_top_tests,
    "refunds": export_refunds_list,
    "registrations": export_registrations_by_branch,
}


def run_excel_export(
    report_type: str,
    period: str,
    db_name: str,
    db_server=None,
    db_user=None,
    db_password=None,
    hospital_name: str = "Hospital",
) -> dict:
    key = (report_type or "collection").lower().strip()
    fn = _EXPORTERS.get(key)
    if not fn:
        return {"error": f"Unknown report_type '{report_type}'. Use: collection, top_tests, refunds, registrations"}
    return fn(
        period=period,
        db_name=db_name,
        db_server=db_server,
        db_user=db_user,
        db_password=db_password,
        hospital_name=hospital_name,
    )