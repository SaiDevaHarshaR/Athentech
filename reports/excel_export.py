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


def _resolve_location(conn, keyword: str):
    if not keyword:
        return None, None
    kw = keyword.strip()
    cur = conn.cursor()
    cur.execute(
        "SELECT LOCATIONID, LOCATIONNAME FROM mstlocation WHERE LOCATIONNAME LIKE ? ORDER BY LOCATIONNAME",
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

    overall = {"CASH": 0.0, "CARD": 0.0, "UPI_ONLINE": 0.0, "CHEQUE": 0.0, "CREDIT": 0.0, "OTHER": 0.0}

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

    for modes in branches.values():
        for mode, amt in modes.items():
            overall[bucket(mode)] += amt
    grand = sum(overall.values())

    wb = Workbook()
    ws = wb.active
    ws.title = "All Branches"
    headers = ["Branch"] + all_modes + ["Total"]
    hr = _title_row(ws, hospital_name, len(headers))
    _style_header_row(ws, hr, headers)

    row_num = hr + 1
    first_data = row_num
    for branch in sorted(branches.keys()):
        ws.cell(row=row_num, column=1, value=branch)
        for col, mode in enumerate(all_modes, start=2):
            c = ws.cell(row=row_num, column=col, value=branches[branch].get(mode, 0.0))
            c.number_format = "#,##0.00"
        tc = len(all_modes) + 2
        fl, ll = get_column_letter(2), get_column_letter(tc - 1)
        c = ws.cell(row=row_num, column=tc, value=f"=SUM({fl}{row_num}:{ll}{row_num})")
        c.font = Font(bold=True, name="Arial")
        c.number_format = "#,##0.00"
        row_num += 1
    last_data = row_num - 1

    # GRAND TOTAL across all branches
    ws.cell(row=row_num, column=1, value="GRAND TOTAL").font = Font(bold=True, name="Arial")
    for col in range(2, len(all_modes) + 3):
        cl = get_column_letter(col)
        c = ws.cell(row=row_num, column=col, value=f"=SUM({cl}{first_data}:{cl}{last_data})")
        c.font = Font(bold=True, name="Arial")
        c.number_format = "#,##0.00"
    row_num += 2

    # Overall totals (all branches)
    ws.cell(row=row_num, column=1, value="OVERALL (ALL BRANCHES)").font = Font(bold=True, size=12)
    row_num += 1
    overall = {"CASH": 0.0, "CARD": 0.0, "UPI_ONLINE": 0.0, "CHEQUE": 0.0, "CREDIT": 0.0, "OTHER": 0.0}

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

    for modes in branches.values():
        for mode, amt in modes.items():
            overall[bucket(mode)] += amt
    grand = sum(overall.values())

    for label_s, val in [
        ("Total Cash", overall["CASH"]),
        ("Total Credit Card", overall["CARD"]),
        ("Total Cheque/Online/UPI Received", overall["UPI_ONLINE"] + overall["CHEQUE"]),
        ("Total UPI/Online", overall["UPI_ONLINE"]),
        ("Total Cheque", overall["CHEQUE"]),
        ("Credits", overall["CREDIT"]),
        ("Other", overall["OTHER"]),
        ("GRAND TOTAL (all modes, all branches)", grand),
        ("Total Cash in Hand", overall["CASH"]),
        ("Total Online/UPI in Hand", overall["UPI_ONLINE"]),
        ("Core business cash collected", overall["CASH"]),
        ("Total cash received", overall["CASH"]),
    ]:
        ws.cell(row=row_num, column=1, value=label_s)
        c = ws.cell(row=row_num, column=2, value=val)
        c.number_format = "#,##0.00"
        if "GRAND" in label_s:
            c.font = Font(bold=True, name="Arial")
        row_num += 1

    safe = re.sub(r"[^A-Za-z0-9_]", "_", label)
    return _save(wb, f"collection_all_branches_{safe}_{date.today().isoformat()}.xlsx", label)


def export_single_branch_collection(
    period, location_keyword, db_name, db_server=None, db_user=None, db_password=None, hospital_name="Hospital",
):
    if not location_keyword:
        return {"error": "Month/year export needs a branch. Example: export excel this month Uppal"}

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
    _style_header_row(ws, hr, headers)

    r = hr + 1
    ws.cell(row=r, column=1, value=f"Branch: {matched if False else list(branches.keys())}")  # fix below