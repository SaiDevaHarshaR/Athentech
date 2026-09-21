"""
HIS (Hospital) intent dispatcher — separate from agent/intents.py
(LIS/diagnostic), per institution.institution_type. No shared tables
or logic between the two by design.

Confirmed real tables so far (via direct SSMS describe_table, not
guessed):
  tblIpBeds       — bed master (BEDID, BEDNO, ROOMID, BEDCHARGES, ACTIVE)
  tblBedOccupancy — patient admission record (UHID, IPNO, PatName,
                    Age, Gender, DocId, TotalAmt/PaidAmt/DueAmt)
  tblIpBedsDtl    — bed assignment (IPNO -> BEDID, ALLOTDT, LEAVEDT,
                    isPresent, isVacated) — the real link table
  tblIpDischarge  — discharge clinical summary (joins via IPNO)

Confirmed join chain:
  tblBedOccupancy.IPNO = tblIpBedsDtl.IPNO
  tblIpBedsDtl.BEDID = tblIpBeds.BEDID
  tblBedOccupancy.IPNO = tblIpDischarge.IPNO
"""

import json
from database.connection import get_hospital_connection

_ALLOWED_ROLES = ("admin", "doctor", "reception")


def _dashboard_card(**kwargs) -> str:
    return "```dashboard-card\n" + json.dumps(kwargs) + "\n```"


def _list_card(**kwargs) -> str:
    return "```list-card\n" + json.dumps(kwargs) + "\n```"


def _conn(db_name, db_server, db_user, db_password):
    return get_hospital_connection(db_name, db_server, db_user, db_password)


# ---------- bed_occupancy_count ----------
def _handle_bed_occupancy_count(q, role, db_name, db_server, db_user, db_password, matched_keyword=None):
    if role not in _ALLOWED_ROLES:
        return "Error: your role does not have access to this data."
    conn = _conn(db_name, db_server, db_user, db_password)
    if not conn:
        return "Error: could not connect to the hospital database."
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM tblIpBedsDtl WHERE isPresent = 1"
        )
        occupied = cursor.fetchone()[0]

        cursor.execute(
            "SELECT COUNT(*) FROM tblIpBeds WHERE ACTIVE = 1"
        )
        total = cursor.fetchone()[0]

        vacant = max(0, total - occupied)
        pct = round((occupied / total) * 100, 1) if total else 0

        return _dashboard_card(
            icon="🛏️", title="Bed Occupancy",
            stats=[
                {"label": "OCCUPIED", "value": f"{occupied:,}"},
                {"label": "VACANT", "value": f"{vacant:,}"},
                {"label": "TOTAL BEDS", "value": f"{total:,}"},
                {"label": "OCCUPANCY %", "value": f"{pct}%"},
            ],
        )
    except Exception as e:
        return f"Error: {e}"
    finally:
        conn.close()


# ---------- currently_admitted_patients ----------
def _handle_currently_admitted(q, role, db_name, db_server, db_user, db_password, matched_keyword=None):
    if role not in _ALLOWED_ROLES:
        return "Error: your role does not have access to this data."
    conn = _conn(db_name, db_server, db_user, db_password)
    if not conn:
        return "Error: could not connect to the hospital database."
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT TOP 15 bo.PatName, bo.UHID, bo.IPNO, bo.Age, bo.Gender, bd.BEDID, bd.ALLOTDT "
            "FROM tblBedOccupancy bo "
            "JOIN tblIpBedsDtl bd ON bo.IPNO = bd.IPNO "
            "WHERE bd.isPresent = 1 "
            "ORDER BY bd.ALLOTDT DESC"
        )
        rows = cursor.fetchall()
        if not rows:
            return "No patients currently admitted."
        return _list_card(
            icon="🏥", title="Currently Admitted Patients",
            intro=f"{len(rows)} most recent (of those currently admitted):",
            items=[
                {"primary": name, "fields": [
                    f"IPNO: {ipno}", f"UHID: {uhid}", f"{age} yrs · {gender}",
                    f"Bed: {bedid}", f"Admitted: {allotdt}",
                ]}
                for name, uhid, ipno, age, gender, bedid, allotdt in rows
            ],
        )
    except Exception as e:
        return f"Error: {e}"
    finally:
        conn.close()


# ---------- patient_admission_lookup ----------
def _handle_admission_lookup(q, role, db_name, db_server, db_user, db_password, matched_keyword=None):
    if role not in _ALLOWED_ROLES:
        return "Error: your role does not have access to this data."
    import re
    m = re.search(r"\b([A-Za-z]{2,6}\d{3,})\b", q.upper())
    if not m:
        return None
    identifier = m.group(1)
    conn = _conn(db_name, db_server, db_user, db_password)
    if not conn:
        return "Error: could not connect to the hospital database."
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT PatName, UHID, IPNO, Age, Gender, TotalAmt, PaidAmt, DueAmt "
            "FROM tblBedOccupancy WHERE UHID = ? OR IPNO = ?",
            (identifier, identifier),
        )
        row = cursor.fetchone()
        if not row:
            return f"No admission record found for '{identifier}'."
        name, uhid, ipno, age, gender, total, paid, due = row
        return _dashboard_card(
            icon="🏥", title=f"Admission · {name}", subtitle=f"IPNO {ipno}",
            stats=[
                {"label": "UHID", "value": uhid},
                {"label": "AGE/GENDER", "value": f"{age} / {gender}"},
                {"label": "TOTAL", "value": f"₹{float(total or 0):,.0f}"},
                {"label": "PAID", "value": f"₹{float(paid or 0):,.0f}"},
                {"label": "DUE", "value": f"₹{float(due or 0):,.0f}"},
            ],
        )
    except Exception as e:
        return f"Error: {e}"
    finally:
        conn.close()


def _resolve_location(q: str, cursor):
    """
    Real location resolution using tblHOSPDTLS (confirmed real branch
    master — LCODE + LocName). Returns (lcode, matched_name) or
    (None, None) if no location was named in the question — callers
    treat None as "all branches combined", not an error.
    """
    strip_words = [
        "today", "yesterday", "this month", "last month", "this year",
        "for", "at", "in", "on", "revenue", "collection", "op", "ip",
    ]
    import re
    text = q
    for w in sorted(strip_words, key=len, reverse=True):
        text = re.sub(rf"\b{re.escape(w)}\b", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\b20\d{2}-\d{2}-\d{2}\b", " ", text).strip()
    if not text:
        return None, None

    cursor.execute("SELECT LCODE, LocName FROM tblHOSPDTLS WHERE LocName LIKE ?", (f"%{text}%",))
    rows = cursor.fetchall()
    if len(rows) == 1:
        return rows[0][0], rows[0][1]
    return None, None


from datetime import date, timedelta
import re

class _UnrecognizedPeriod(Exception):
    pass


def _period_dates(q: str):
    """
    Returns (date_from, date_to_exclusive, label).
    date_to is exclusive (use >= from AND < to).
    Raises _UnrecognizedPeriod if nothing usable is found.
    """
    today = date.today()
    q = (q or "").lower()

    if "yesterday" in q:
        d = today - timedelta(days=1)
        return d.isoformat(), (d + timedelta(days=1)).isoformat(), "Yesterday"
    if "last week" in q:
        start = today - timedelta(days=today.weekday() + 7)
        return start.isoformat(), (start + timedelta(days=7)).isoformat(), "Last Week"
    if "this week" in q:
        start = today - timedelta(days=today.weekday())
        return start.isoformat(), (today + timedelta(days=1)).isoformat(), "This Week"
    if "last month" in q:
        first_this = today.replace(day=1)
        last_start = (first_this - timedelta(days=1)).replace(day=1)
        return last_start.isoformat(), first_this.isoformat(), "Last Month"
    if "this month" in q:
        start = today.replace(day=1)
        return start.isoformat(), (today + timedelta(days=1)).isoformat(), "This Month"
    if "last year" in q:
        y = today.year - 1
        return f"{y}-01-01", f"{today.year}-01-01", str(y)
    if "this year" in q:
        return f"{today.year}-01-01", (today + timedelta(days=1)).isoformat(), "This Year"

    # YYYY-MM-DD
    m = re.search(r"\b(20\d{2})-(\d{2})-(\d{2})\b", q)
    if m:
        d = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        return d.isoformat(), (d + timedelta(days=1)).isoformat(), d.isoformat()

    months = {
        "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
        "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
        "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7, "aug": 8,
        "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
    }

    # "4th september 2025" / "september 4 2025"
    m = re.search(
        r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\s*(20\d{2})?\b",
        q,
    )
    if m:
        day, mon_s, yr = int(m.group(1)), m.group(2).lower(), m.group(3)
        mon = next(v for k, v in months.items() if mon_s.startswith(k[:3]))
        year = int(yr) if yr else today.year
        d = date(year, mon, day)
        return d.isoformat(), (d + timedelta(days=1)).isoformat(), d.isoformat()

    m = re.search(
        r"\b(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\s+(\d{1,2})(?:st|nd|rd|th)?\s*(20\d{2})?\b",
        q,
    )
    if m:
        mon_s, day, yr = m.group(1).lower(), int(m.group(2)), m.group(3)
        mon = next(v for k, v in months.items() if mon_s.startswith(k[:3]))
        year = int(yr) if yr else today.year
        d = date(year, mon, day)
        return d.isoformat(), (d + timedelta(days=1)).isoformat(), d.isoformat()

    # Bare month: "july" / "july 2025"
    m = re.search(
        r"\b(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\b(?:\s+(20\d{2}))?",
        q,
    )
    if m:
        mon_s, yr = m.group(1).lower(), m.group(2)
        mon = next(v for k, v in months.items() if mon_s.startswith(k[:3]))
        year = int(yr) if yr else today.year
        start = date(year, mon, 1)
        end = date(year + 1, 1, 1) if mon == 12 else date(year, mon + 1, 1)
        return start.isoformat(), end.isoformat(), f"{start.strftime('%b %Y')}"

    # Bare year: "2025"
    m = re.search(r"\b(20\d{2})\b", q)
    if m:
        y = int(m.group(1))
        return f"{y}-01-01", f"{y + 1}-01-01", str(y)

    if "today" in q:
        return today.isoformat(), (today + timedelta(days=1)).isoformat(), "Today"

    # Default: today (HIS ops questions often omit the word)
    return today.isoformat(), (today + timedelta(days=1)).isoformat(), "Today"
# ---------- day_collection (real, from confirmed dbo.Daycollection_net) ----------
def _handle_day_collection(q, role, db_name, db_server, db_user, db_password, matched_keyword=None):
    if role not in _ALLOWED_ROLES:
        return "Error: your role does not have access to this data."
    try:
        date_from, date_to, label = _period_dates(q)
    except _UnrecognizedPeriod:
        return None

    conn = _conn(db_name, db_server, db_user, db_password)
    if not conn:
        return "Error: could not connect to the hospital database."
    try:
        cursor = conn.cursor()
        # SAME joins/tables — only date predicate widened
        cursor.execute("""
            SELECT
                SUM(CASE WHEN MODE = 0 THEN AMTPAID ELSE 0 END) AS CASH,
                SUM(CASE WHEN MODE = 1 THEN AMTPAID ELSE 0 END) AS CARD,
                SUM(CASE WHEN MODE > 1 THEN AMTPAID ELSE 0 END) AS ONLINE,
                SUM(AMTPAID) AS TOTAL
            FROM tblOPPAYDTLS P
            INNER JOIN tblOPRegistration R
                ON P.BILLDT = R.REGDT AND P.BILLNO = R.Billno AND P.TTYPE = R.TTYPE
            WHERE CAST(DTPAID AS DATE) >= ? AND CAST(DTPAID AS DATE) < ?
              AND P.TTYPE = 0
              AND ISNULL(R.Cancelled, 0) = 0
              AND ISNULL(Refund, 0) = 0
        """, (date_from, date_to))
        row = cursor.fetchone()
        cash, card, online, total = (float(x or 0) for x in row) if row else (0, 0, 0, 0)
        return _dashboard_card(
            icon="💰", title="Day Collection", subtitle=label,
            stats=[
                {"label": "TOTAL COLLECTED", "value": f"₹{total:,.0f}"},
                {"label": "CASH", "value": f"₹{cash:,.0f}"},
                {"label": "CARD", "value": f"₹{card:,.0f}"},
                {"label": "ONLINE", "value": f"₹{online:,.0f}"},
            ],
        )
    except Exception as e:
        return f"Error: {e}"
    finally:
        conn.close()

# ---------- investigations_ordered (real, from confirmed dbo.R_Investigations) ----------
def _handle_investigations_ordered(q, role, db_name, db_server, db_user, db_password, matched_keyword=None):
    if role not in _ALLOWED_ROLES:
        return "Error: your role does not have access to this data."
    from datetime import date, timedelta
    target_date = _resolve_target_date(q)

    conn = _conn(db_name, db_server, db_user, db_password)
    if not conn:
        return "Error: could not connect to the hospital database."
    try:
        cursor = conn.cursor()
        # Real formula from confirmed dbo.R_Investigations (OP branch only,
        # for now — IP-CASH/IP-CREDIT branches need the same treatment
        # later). CAN_FLG='N' means not cancelled; isIP<>1 means OP.
        cursor.execute("""
            SELECT TOP 15
                D.DocName AS CONSULTANT, ST.DeptName AS INVDEPT, S.INVNAME,
                DT.INVRATE AS CHARGE, I.Initial + '' + I.PatName AS PATIENTNAME
            FROM tblPatReqTransDet DT
            INNER JOIN tblInvMst S ON CONVERT(varchar, S.INVCODE) = DT.INVCODE
            INNER JOIN tblDept ST ON ST.DeptID = S.DeptID
            INNER JOIN tblPatReqHdr FM ON FM.REQNO = DT.REQNO AND FM.REQDT = DT.REQDT AND DT.lcode = FM.lcode
            INNER JOIN tblPatInfo I ON I.UHID = FM.UHID
            INNER JOIN tblDoctorInfo D ON D.DOCID = FM.DocId
            INNER JOIN tblDoctorDept DD ON DD.DoctrDeptID = D.DoctrDeptID
            WHERE ISNULL(FM.CAN_FLG, '') = 'N' AND ISNULL(FM.isIP, 0) <> 1
              AND CAST(FM.REQDT AS DATE) = ?
            ORDER BY FM.REQDT DESC
        """, (target_date,))
        rows = cursor.fetchall()
        if not rows:
            return f"No investigations ordered on {target_date} (OP)."

        return _list_card(
            icon="🧪", title="Investigations Ordered (OP)", intro=f"{target_date} — {len(rows)} shown:",
            items=[
                {"primary": inv_name, "fields": [
                    f"Patient: {pat}", f"Consultant: {doc}", f"Dept: {dept}", f"₹{float(charge or 0):,.0f}",
                ]}
                for doc, dept, inv_name, charge, pat in rows
            ],
        )
    except Exception as e:
        return f"Error: {e}"
    finally:
        conn.close()


# ---------- op_revenue (real, simplified from confirmed dbo.DAYWISEOP) ----------
def _handle_op_revenue(q, role, db_name, db_server, db_user, db_password, matched_keyword=None):
    if role not in _ALLOWED_ROLES:
        return "Error: your role does not have access to this data."
    target_date = _resolve_target_date(q)

    conn = _conn(db_name, db_server, db_user, db_password)
    if not conn:
        return "Error: could not connect to the hospital database."
    try:
        cursor = conn.cursor()
        lcode, loc_name = _resolve_location(q, cursor)
        loc_sql = " AND LCODE = ?" if lcode else ""

        params1 = (target_date, lcode) if lcode else (target_date,)
        cursor.execute(f"""
            SELECT
                SUM(CASE WHEN TTYPE = 4 THEN AMTPAID ELSE 0 END) AS Registration,
                SUM(CASE WHEN TTYPE = 3 THEN AMTPAID ELSE 0 END) AS Services,
                SUM(CASE WHEN TTYPE = 2 THEN AMTPAID ELSE 0 END) AS Operations,
                SUM(AMTPAID) AS TOTAL
            FROM tblOPPAYDTLS
            WHERE CAST(DTPAID AS DATE) = ? AND TTYPE IN (2, 3, 4){loc_sql}
        """, params1)
        reg, services, ops, op_total = (float(x or 0) for x in cursor.fetchone())

        params2 = (target_date, lcode) if lcode else (target_date,)
        loc_sql_qualified = " AND P.LCODE = ?" if lcode else ""
        cursor.execute(f"""
            SELECT ISNULL(SUM(P.AMTPAID), 0)
            FROM tblOPPAYDTLS P
            INNER JOIN tblOPRegistration R ON R.Billno = P.BILLNO AND R.TTYPE = P.TTYPE
            WHERE CAST(P.DTPAID AS DATE) = ? AND R.TTYPE = 0 AND R.Cancelled = 'False'{loc_sql_qualified}
        """, params2)
        consultation = float(cursor.fetchone()[0] or 0)

        params3 = (target_date, lcode) if lcode else (target_date,)
        loc_sql_qualified2 = " AND PD.LCODE = ?" if lcode else ""
        cursor.execute(f"""
            SELECT ISNULL(SUM(PD.AMTPAID), 0)
            FROM tblPATREQPYMTDET PD
            INNER JOIN tblPatReqHdr H ON H.REQDT = PD.REQDT AND H.REQNO = PD.REQNO
            WHERE CAST(PD.DTPAID AS DATE) = ? AND H.CAN_FLG = 'N'{loc_sql_qualified2}
        """, params3)
        oplab = float(cursor.fetchone()[0] or 0)

        grand_total = op_total + consultation + oplab
        subtitle = f"{target_date}" + (f" · {loc_name}" if loc_name else " · All Branches")

        return _dashboard_card(
            icon="🏥", title="OP Revenue", subtitle=subtitle,
            stats=[
                {"label": "TOTAL", "value": f"₹{grand_total:,.0f}"},
                {"label": "REGISTRATION", "value": f"₹{reg:,.0f}"},
                {"label": "CONSULTATION", "value": f"₹{consultation:,.0f}"},
                {"label": "SERVICES", "value": f"₹{services:,.0f}"},
                {"label": "OPERATIONS", "value": f"₹{ops:,.0f}"},
                {"label": "OP LAB", "value": f"₹{oplab:,.0f}"},
            ],
        )
    except Exception as e:
        return f"Error: {e}"
    finally:
        conn.close()


# ---------- ip_revenue (real, simplified from confirmed dbo.DAYWISEIP) ----------
def _handle_ip_revenue(q, role, db_name, db_server, db_user, db_password, matched_keyword=None):
    if role not in _ALLOWED_ROLES:
        return "Error: your role does not have access to this data."
    target_date = _resolve_target_date(q)

    conn = _conn(db_name, db_server, db_user, db_password)
    if not conn:
        return "Error: could not connect to the hospital database."
    try:
        cursor = conn.cursor()
        lcode, loc_name = _resolve_location(q, cursor)
        loc_sql = " AND LCODE = ?" if lcode else ""

        p1 = (target_date, lcode) if lcode else (target_date,)
        cursor.execute(f"""
            SELECT ISNULL(SUM(PAIDAMT), 0)
            FROM tblIPAdvances WHERE CAST(BILLDT AS DATE) = ? AND TTYPE = 0{loc_sql}
        """, p1)
        advance = float(cursor.fetchone()[0] or 0)

        p2 = (target_date, lcode) if lcode else (target_date,)
        cursor.execute(f"""
            SELECT ISNULL(SUM(AMTPAID), 0)
            FROM tblIPPAYDTLS WHERE CAST(DTPAID AS DATE) = ? AND TTYPE = 21{loc_sql}
        """, p2)
        final_cash = float(cursor.fetchone()[0] or 0)

        p3 = (target_date, lcode) if lcode else (target_date,)
        cursor.execute(f"""
            SELECT ISNULL(SUM(AMTPAID), 0)
            FROM tblIPCORPPAYDTLS WHERE CAST(DTPAID AS DATE) = ? AND TTYPE = 25{loc_sql}
        """, p3)
        final_corp = float(cursor.fetchone()[0] or 0)

        total = advance + final_cash + final_corp
        subtitle = f"{target_date}" + (f" · {loc_name}" if loc_name else " · All Branches")

        return _dashboard_card(
            icon="🛏️", title="IP Revenue", subtitle=subtitle,
            stats=[
                {"label": "TOTAL", "value": f"₹{total:,.0f}"},
                {"label": "ADVANCES", "value": f"₹{advance:,.0f}"},
                {"label": "FINAL BILL (CASH)", "value": f"₹{final_cash:,.0f}"},
                {"label": "FINAL BILL (CORPORATE)", "value": f"₹{final_corp:,.0f}"},
            ],
        )
    except Exception as e:
        return f"Error: {e}"
    finally:
        conn.close()


# ---------- test_catalog (real, from confirmed dbo.R_BranchInvestigationMaster) ----------
def _handle_test_catalog(q, role, db_name, db_server, db_user, db_password, matched_keyword=None):
    if role not in _ALLOWED_ROLES:
        return "Error: your role does not have access to this data."
    conn = _conn(db_name, db_server, db_user, db_password)
    if not conn:
        return "Error: could not connect to the hospital database."
    try:
        cursor = conn.cursor()
        # Real query from confirmed dbo.R_BranchInvestigationMaster —
        # per-branch test catalog with real rates.
        cursor.execute("""
            SELECT TOP 15 M.INVNAME, D.DeptName, DT.RATE
            FROM tblInvMst M
            INNER JOIN tblInvDetails DT ON DT.INVCODE = M.INVCODE
            INNER JOIN tblDept D ON D.DeptID = M.DeptID
            ORDER BY M.INVNAME
        """)
        rows = cursor.fetchall()
        if not rows:
            return "No investigations found in the catalog."
        return _list_card(
            icon="🧪", title="Investigation Catalog",
            intro=f"{len(rows)} shown:",
            items=[
                {"primary": name, "fields": [f"Dept: {dept}", f"₹{float(rate or 0):,.0f}"]}
                for name, dept, rate in rows
            ],
        )
    except Exception as e:
        return f"Error: {e}"
    finally:
        conn.close()


# ---------- patient_search (real, from confirmed dbo.PatientData) ----------
def _handle_patient_search(q, role, db_name, db_server, db_user, db_password, matched_keyword=None):
    if role not in _ALLOWED_ROLES:
        return "Error: your role does not have access to this data."
    import re
    m = re.search(r"(?:find|search|lookup)\s+patient\s+([a-zA-Z ]+)", q)
    if not m:
        return None
    name_search = m.group(1).strip()

    conn = _conn(db_name, db_server, db_user, db_password)
    if not conn:
        return "Error: could not connect to the hospital database."
    try:
        cursor = conn.cursor()
        # Real query base from confirmed dbo.PatientData, adapted with a
        # WHERE filter (the original has none — returns the whole table,
        # unsafe for a real lookup) and TOP 10 for a real name search.
        cursor.execute("""
            SELECT TOP 10 Initial + ' ' + PatName AS FullName,
                CONVERT(varchar, Age) + ' ' + CASE AgeType WHEN 0 THEN 'Yrs' WHEN 1 THEN 'Months' ELSE 'Days' END AS AgeStr,
                Gender, PHONE
            FROM tblPatInfo
            WHERE PatName LIKE ?
        """, (f"%{name_search}%",))
        rows = cursor.fetchall()
        if not rows:
            return f"No patients found matching '{name_search}'."
        return _list_card(
            icon="🧑‍🤝‍🧑", title="Patient Search",
            intro=f"Matching '{name_search}':",
            items=[
                {"primary": name, "fields": [age, gender, f"Phone: {phone}" if phone else "Phone: -"]}
                for name, age, gender, phone in rows
            ],
        )
    except Exception as e:
        return f"Error: {e}"
    finally:
        conn.close()


# ---------- equipment_usage (real, from confirmed dbo.MedicalEquipmentCollection Details) ----------
def _handle_equipment_usage(q, role, db_name, db_server, db_user, db_password, matched_keyword=None):
    if role not in _ALLOWED_ROLES:
        return "Error: your role does not have access to this data."
    from datetime import date, timedelta
    from_date = (date.today() - timedelta(days=30)).isoformat() if "month" in q else (date.today() - timedelta(days=1)).isoformat()
    to_date = date.today().isoformat()

    conn = _conn(db_name, db_server, db_user, db_password)
    if not conn:
        return "Error: could not connect to the hospital database."
    try:
        cursor = conn.cursor()
        # Real query from confirmed dbo.MedicalEquipmentCollection
        # (Details branch) — discharged IP patients' equipment usage.
        cursor.execute("""
            SELECT TOP 15 doc.DocName, I.Initial + I.PatName AS Patient, M.MEName, ED.Duration, ED.AMOUNT
            FROM tblIPRegistration IP
            INNER JOIN tblIPMachineEquipmentMst E ON CONVERT(varchar, E.IPNO) = IP.IPNO AND E.LCODE = IP.LCODE
            INNER JOIN tblIPMachineEquipmentDtls ED ON ED.BILLNO = E.BILLNO AND ED.BILLDT = E.BILLDT
                AND ED.LCODE = E.LCODE AND CONVERT(varchar, ED.IPNO) = E.IPNO
            INNER JOIN tblIPMachineEquipment M ON M.MEID = ED.MEID
            INNER JOIN tblPatInfo I ON I.UHID = CONVERT(varchar, IP.UHID)
            INNER JOIN tblDoctorInfo doc ON doc.DocId = IP.DocId
            WHERE IP.IsDischarge = 1 AND ED.RATE > 0
              AND IP.REGDT BETWEEN ? AND ?
            ORDER BY doc.DocName, IP.REGDT
        """, (from_date, to_date))
        rows = cursor.fetchall()
        if not rows:
            return f"No equipment usage recorded for discharged patients between {from_date} and {to_date}."
        return _list_card(
            icon="🩺", title="Equipment Usage", intro=f"{from_date} to {to_date} — {len(rows)} shown:",
            items=[
                {"primary": equip, "fields": [f"Patient: {pat}", f"Doctor: {doc}", f"{dur} hrs", f"₹{float(amt or 0):,.0f}"]}
                for doc, pat, equip, dur, amt in rows
            ],
        )
    except Exception as e:
        return f"Error: {e}"
    finally:
        conn.close()


# ---------- appointments (real, from confirmed tblDocAppointments) ----------
def _handle_appointments(q, role, db_name, db_server, db_user, db_password, matched_keyword=None):
    if role not in _ALLOWED_ROLES:
        return "Error: your role does not have access to this data."
    target_date = _resolve_target_date(q)

    conn = _conn(db_name, db_server, db_user, db_password)
    if not conn:
        return "Error: could not connect to the hospital database."
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT TOP 15 A.PatientName, D.DocName, A.FromTime, A.ToTime, A.MobileNumber
            FROM tblDocAppointments A
            LEFT JOIN tblDoctorInfo D ON D.DocId = A.DocId
            WHERE CAST(A.AppointDt AS DATE) = ?
            ORDER BY A.FromTime
        """, (target_date,))
        rows = cursor.fetchall()
        if not rows:
            return f"No appointments found for {target_date}."
        return _list_card(
            icon="📅", title="Appointments", intro=f"{target_date} — {len(rows)} shown:",
            items=[
                {"primary": pat, "fields": [f"Dr. {doc or 'Unknown'}", f"{ft}–{tt}", f"Ph: {mob}" if mob else "Ph: -"]}
                for pat, doc, ft, tt, mob in rows
            ],
        )
    except Exception as e:
        return f"Error: {e}"
    finally:
        conn.close()


# ---------- low_stock (real, from confirmed viewstock) ----------
def _handle_low_stock(q, role, db_name, db_server, db_user, db_password, matched_keyword=None):
    if role not in _ALLOWED_ROLES:
        return "Error: your role does not have access to this data."
    conn = _conn(db_name, db_server, db_user, db_password)
    if not conn:
        return "Error: could not connect to the hospital database."
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT TOP 15 MEDNM, MedDeptName, CurrQty, ReqQty
            FROM viewstock
            WHERE CurrQty < ReqQty
            ORDER BY (ReqQty - CurrQty) DESC
        """)
        rows = cursor.fetchall()
        if not rows:
            return "No items currently below their required stock level."
        return _list_card(
            icon="💊", title="Low Stock Items", intro=f"{len(rows)} items below required level:",
            items=[
                {"primary": name, "fields": [f"Dept: {dept}", f"Current: {int(cur or 0)}", f"Required: {int(req or 0)}"]}
                for name, dept, cur, req in rows
            ],
        )
    except Exception as e:
        return f"Error: {e}"
    finally:
        conn.close()


# ---------- doctor_lookup (real, from confirmed tblDoctorInfo) ----------
def _handle_doctor_lookup(q, role, db_name, db_server, db_user, db_password, matched_keyword=None):
    if role not in _ALLOWED_ROLES:
        return "Error: your role does not have access to this data."
    import re
    m = re.search(r"(?:find|search|lookup)\s+doctor\s+([a-zA-Z ]+)", q)
    if not m:
        return None
    name_search = m.group(1).strip()

    conn = _conn(db_name, db_server, db_user, db_password)
    if not conn:
        return "Error: could not connect to the hospital database."
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT TOP 10 DocName, DoctrDeptID FROM tblDoctorInfo WHERE DocName LIKE ?
        """, (f"%{name_search}%",))
        rows = cursor.fetchall()
        if not rows:
            return f"No doctors found matching '{name_search}'."
        return _list_card(
            icon="👨‍⚕️", title="Doctor Search", intro=f"Matching '{name_search}':",
            items=[{"primary": name, "fields": [f"Dept ID: {dept}"]} for name, dept in rows],
        )
    except Exception as e:
        return f"Error: {e}"
    finally:
        conn.close()


# ---------- expenditure (real, from confirmed dbo.R_EXPENDITURE) ----------
def _handle_expenditure(q, role, db_name, db_server, db_user, db_password, matched_keyword=None):
    if role not in _ALLOWED_ROLES:
        return "Error: your role does not have access to this data."
    target_date = _resolve_target_date(q)

    conn = _conn(db_name, db_server, db_user, db_password)
    if not conn:
        return "Error: could not connect to the hospital database."
    try:
        cursor = conn.cursor()
        # Real query from confirmed dbo.R_EXPENDITURE (All/ALL branch) —
        # combined credit + debit vouchers for one date.
        cursor.execute("""
            SELECT 'Debit' AS VoucherType, V.VoucherNo, AC.AccountHeaderNAME, -Amount AS Amount, Remarks
            FROM tblVoucherGeneration V
            INNER JOIN tblAccountHeader AC ON AC.AccountHeaderID = V.AccHeaderId
            WHERE V.VoucherType = 0 AND CAST(V.VoucherDt AS DATE) = ?
            UNION ALL
            SELECT 'Credit' AS VoucherType, V.VoucherNo, AC.AccountHeaderNAME, Amount, Remarks
            FROM tblVoucherGeneration V
            INNER JOIN tblAccountHeader AC ON AC.AccountHeaderID = V.AccHeaderId
            WHERE V.VoucherType = 1 AND CAST(V.VoucherDt AS DATE) = ?
        """, (target_date, target_date))
        rows = cursor.fetchall()
        if not rows:
            return f"No expenditure vouchers recorded on {target_date}."

        total = sum(float(amt or 0) for _, _, _, amt, _ in rows)
        return _list_card(
            icon="🧾", title="Expenditure Vouchers", intro=f"{target_date} — Net: ₹{total:,.0f} ({len(rows)} entries):",
            items=[
                {"primary": f"{vtype} · {header}", "fields": [f"Voucher #{vno}", f"₹{float(amt or 0):,.0f}", remarks or "-"]}
                for vtype, vno, header, amt, remarks in rows[:15]
            ],
        )
    except Exception as e:
        return f"Error: {e}"
    finally:
        conn.close()


_INTENTS_HIS = [
    (["expenditure", "vouchers", "expense", "expenses today", "expenses yesterday"], _handle_expenditure),
    (["appointments", "appointment list", "today's appointments", "doctor appointments"],
     _handle_appointments),
    (["low stock", "stock below", "reorder level", "stock report"], _handle_low_stock),
    (["find doctor", "search doctor", "lookup doctor"], _handle_doctor_lookup),
    (["equipment usage", "equipment collection", "medical equipment"], _handle_equipment_usage),
    (["investigation catalog", "test catalog", "list investigations", "list tests", "all tests"],
     _handle_test_catalog),
    (["find patient", "search patient", "lookup patient"], _handle_patient_search),
    (["op revenue", "outpatient revenue", "op collection", "outpatient collection", "opd revenue"],
     _handle_op_revenue),
    (["ip revenue", "inpatient revenue", "ip collection", "inpatient collection"],
     _handle_ip_revenue),
    (["day collection", "today's collection", "collection today", "collection yesterday",
      "collection this month", "collection this year", "total collection"],
     _handle_day_collection),
    (["investigations ordered", "tests ordered", "lab tests today", "investigations today",
      "investigations this month"],
     _handle_investigations_ordered),
    (["beds occupied", "bed occupancy", "occupied beds", "how many beds", "bed status",
      "beds available", "available beds"],
     _handle_bed_occupancy_count),
    (["currently admitted", "admitted patients", "who is admitted", "patients admitted"],
     _handle_currently_admitted),
    (["admission for", "admission details", "admitted uhid", "ipno"], _handle_admission_lookup),
]


def try_intent_his(question: str, role: str, db_name: str, db_server=None, db_user=None, db_password=None):
