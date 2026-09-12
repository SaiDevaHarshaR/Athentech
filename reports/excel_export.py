"""
Excel export — all-branches collection breakdown. Generates a real
.xlsx file server-side, saved to a local exports directory. Wire the
returned path into your FastAPI static-file serving to give the user
an actual download link.
"""

import os
import re
from datetime import date, timedelta

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils import get_column_letter

from database.connection import get_hospital_connection

EXPORT_DIR = "exports"
os.makedirs(EXPORT_DIR, exist_ok=True)


def _period_dates(period_keyword: str):
    """Same period-resolution pattern used everywhere else in this codebase."""
    today = date.today()
    p = (period_keyword or "today").lower()
    if p == "yesterday":
        d = today - timedelta(days=1)
        return d.isoformat(), (d + timedelta(days=1)).isoformat(), "Yesterday"
    if p == "this_month":
        start = today.replace(day=1)
        return start.isoformat(), (today + timedelta(days=1)).isoformat(), "This Month"
    if p == "last_month":
        first_this = today.replace(day=1)
        last_month_start = (first_this - timedelta(days=1)).replace(day=1)
        return last_month_start.isoformat(), first_this.isoformat(), "Last Month"
    return today.isoformat(), (today + timedelta(days=1)).isoformat(), "Today"


def export_all_branches_collection(
    period: str,
    db_name: str,
    db_server=None, db_user=None, db_password=None,
) -> dict:
    """
    Returns {"path": "<local file path>", "filename": "<name>"} on
    success, or {"error": "..."} on failure. Caller is responsible for
    serving the file (e.g. FastAPI FileResponse or a static mount).
    """
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

    # Pivot: branch -> {mode: amount}
    branches = {}
    all_modes = set()
    for branch, mode, amt in rows:
        branches.setdefault(branch, {})[mode] = float(amt or 0)
        all_modes.add(mode)
    all_modes = sorted(all_modes)

    wb = Workbook()
    ws = wb.active
    ws.title = "Collection"

    header_font = Font(bold=True, color="FFFFFF", name="Arial")
    header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")

    headers = ["Branch"] + all_modes + ["Total"]
    for col, h in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=col, value=h)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center")

    row_num = 2
    grand_total_row_refs = []
    for branch in sorted(branches.keys()):
        ws.cell(row=row_num, column=1, value=branch).font = Font(name="Arial")
        for col, mode in enumerate(all_modes, start=2):
            amt = branches[branch].get(mode, 0.0)
            ws.cell(row=row_num, column=col, value=amt).font = Font(name="Arial")
            ws.cell(row=row_num, column=col).number_format = "#,##0"
        total_col = len(all_modes) + 2
        first_mode_col = get_column_letter(2)
        last_mode_col = get_column_letter(total_col - 1)
        ws.cell(row=row_num, column=total_col, value=f"=SUM({first_mode_col}{row_num}:{last_mode_col}{row_num})")
        ws.cell(row=row_num, column=total_col).font = Font(name="Arial", bold=True)
        ws.cell(row=row_num, column=total_col).number_format = "#,##0"
        grand_total_row_refs.append(row_num)
        row_num += 1

    # Grand total row
    total_row = row_num
    ws.cell(row=total_row, column=1, value="GRAND TOTAL").font = Font(bold=True, name="Arial")
    for col in range(2, len(all_modes) + 3):
        col_letter = get_column_letter(col)
        first_data_row = 2
        last_data_row = total_row - 1
        ws.cell(row=total_row, column=col, value=f"=SUM({col_letter}{first_data_row}:{col_letter}{last_data_row})")
        ws.cell(row=total_row, column=col).font = Font(bold=True, name="Arial")
        ws.cell(row=total_row, column=col).number_format = "#,##0"

    # Column widths
    ws.column_dimensions["A"].width = 28
    for col in range(2, len(all_modes) + 3):
        ws.column_dimensions[get_column_letter(col)].width = 14

    safe_label = re.sub(r"[^A-Za-z0-9_]", "_", label)
    filename = f"collection_{safe_label}_{date.today().isoformat()}.xlsx"
    filepath = os.path.join(EXPORT_DIR, filename)
    wb.save(filepath)

    return {"path": filepath, "filename": filename, "period_label": label}