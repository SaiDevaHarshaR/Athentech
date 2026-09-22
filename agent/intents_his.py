"""
HIS (Hospital) intent dispatcher — separate from agent/intents.py
(LIS/diagnostic), per institution.institution_type. No shared tables
or logic between the two by design.

Every date-driven handler uses _period_dates (a real from/to date
RANGE parser — supports "today", "yesterday", "this month", a bare
year like "2026", a bare month like "july", an exact YYYY-MM-DD, etc.)
instead of a single-date match. This matters specifically because this
is STATIC test data (not continuously updated), so "today" almost
never has real data.

=============================================================================
CONFIRMED SCHEMA REFERENCE — direct from AthenTech's own developers,
not guessed/reverse-engineered. Master/detail table pairs + real TTYPE
codes for every transaction type. Use this before guessing a table
name for a new handler.
=============================================================================

--- OP (Outpatient) ---
tblpatinfo              — Registration            TTYPE=4   (where ENTRYDATE=...)
tblOPRegistration       — Consultation             TTYPE=0   (where REGDT=...)
tblTransServicesMst     — Procedure Master         TTYPE=3   (where BILLDT=...)
tblTransServicesDtls    — Procedure Details        TTYPE=3
tblOPAMTTRANS           — OP amount transactions
tblOPPAYDTLS            — OP payment details (CONFIRMED: has BOTH BILLDT and
                          DTPAID as real separate columns — likely bill date
                          vs actual payment date, not interchangeable)
tblOPCredit_Card_Details, tblOPConcessions, tblOPRefunds, tblOPCancellation
tblOPServices           — OP services master

--- IP (Inpatient) ---
tblIPRegistration       — IP Admission             (where REGDT=...)
tblIpBedsDtl            — bed allotment            (ALLOTDT — confirmed, already used)
tblIPAdvances           — IP Advances              TTYPE=0
tblIPTransServicesMst   — IP Procedure Master       TTYPE=1
tblIPTransServicesDtls  — IP Procedure Details      TTYPE=1
tblIPFinalBillMst       — Cash Final Bill MASTER (bill record: ToalAmount,
                          ADVANCEAMT, CONCAMT — NOT the payment table)
tblIPFinalBillDtls      — Cash Final Bill Details   TTYPE=21
tblIPPAYDTLS            — CONFIRMED: actual IP payment table (AMTPAID, DTPAID,
                          BILLDT, TTYPE) — this is what ip_revenue queries
tblIPCorpFinalBillMst   — Credit(insurance) Final Bill Master  TTYPE=25
tblIPCorpFinalBillDtls  — Credit Final Bill Details TTYPE=25
tblIPAMTTRANS, tblIPPAYDTLS, tblIPCredit_Card_Details, tblIPConcessions
  (NOT for Advances/IP Admission), tblIPFinalRefunds, tblIPCancellation
tblIpBeds, tblIpRooms, tblIpRoomType, tblIPFloors — bed/room/floor masters
--- IP Credit (insurance) ---
tblIPCorpAMTTRANS, tblIPCorpPaydtls, tblIPCorpCredit_Card_Details,
tblIPCorpConcessions (NOT for Advances/IP Admission), tblIPCorpFinalRefunds

--- Lab ---
tblPatReqHdr            — lab request header       (where REQDT=...)
tblPatReqTransDet       — lab request line items    (where REQDT=...)
tblAmountTrans, tblPatReqPymtDet, tblCredit_Card_Details, tblConcessions,
tblRefunds, tblCancellation — all keyed off REQDT
tblDept, tblMainDept    — department hierarchy (2 levels)
tblInvMst               — investigation/test master

--- Pharmacy --- (each pair is Master + Details, real TTYPE per transaction type)
tblPharmPurchaseMst/Dtls       — GRN (goods received)         TTYPE=0  (PurchDate)
tblPharmPurchRetMast/Dtls      — GRN Return                   TTYPE=1  (PRBILLDT)
tblPharmSalesMst/Dtls          — OP Sales                     TTYPE=2  (SALEDT)
tblPharmSaleRetMast/Dtls       — OP Sales Return               TTYPE=3  (SALERETDT)
tblPharmipSalesMst/tblPharmIPSalesDtls — IP Sales              TTYPE=4  (SALEDT)
tblPharmIPSaleRetMast/Dtls     — IP Sales Return                TTYPE=5  (SALERETDT)
tblPharmAmountTrans, tblPharmPymtDet, tblPharmCr_Cd_Details, tblPharmConcessions — keyed off BILLDT
tblPharmDepts, tblPharmMedicines — masters
tblPharmDeptIssueMst/Dtls      — inter-department issue        (ISSUEDT)
tblPharmDeptMedDtls            — REAL STOCK TABLE, CONFIRMED via SSMS (MEDID,
                                  BATCHNO, CURRQTY, EXPDT). No name/threshold
                                  column here — join tblPharmMedicines.MEDID for
                                  the name and ROL (Reorder Level)/ROQ.
tblPharmMedicines               — medicine master, CONFIRMED (MEDNM, GENERICNM,
                                  ROL=Reorder Level, ROQ=Reorder Qty)
tblPharmaTrack                 — stock ADJUSTMENTS (separate from stock levels)
=============================================================================
"""

import json
import re
from datetime import date, timedelta

from database.connection import get_hospital_connection

_ALLOWED_ROLES = ("admin", "doctor", "reception")


def _dashboard_card(**kwargs) -> str:
    return "```dashboard-card\n" + json.dumps(kwargs) + "\n```"


def _list_card(**kwargs) -> str:
    return "```list-card\n" + json.dumps(kwargs) + "\n```"


def _conn(db_name, db_server, db_user, db_password):
    return get_hospital_connection(db_name, db_server, db_user, db_password)


class _UnrecognizedPeriod(Exception):
    pass


def _period_dates(q: str):
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

    m = re.search(r"\b(20\d{2})\b", q)
    if m:
        y = int(m.group(1))
        return f"{y}-01-01", f"{y + 1}-01-01", str(y)

    if "today" in q:
        return today.isoformat(), (today + timedelta(days=1)).isoformat(), "Today"

    return today.isoformat(), (today + timedelta(days=1)).isoformat(), "Today"


def _resolve_location(q: str, cursor):
    strip_words = [
        "today", "yesterday", "this month", "last month", "this year", "last year",
        "for", "at", "in", "on", "revenue", "collection", "op", "ip",
        "january", "february", "march", "april", "may", "june", "july",
        "august", "september", "october", "november", "december",
    ]
    text = q
    for w in sorted(strip_words, key=len, reverse=True):
        text = re.sub(rf"\b{re.escape(w)}\b", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\b20\d{2}(-\d{2}-\d{2})?\b", " ", text).strip()
    if not text:
        return None, None

    cursor.execute("SELECT LCODE, LocName FROM tblHOSPDTLS WHERE LocName LIKE ?", (f"%{text}%",))
    rows = cursor.fetchall()
    if len(rows) == 1:
        return rows[0][0], rows[0][1]
    return None, None


# ---------- bed_occupancy_count ----------
def _handle_bed_occupancy_count(q, role, db_name, db_server, db_user, db_password, matched_keyword=None):
    if role not in _ALLOWED_ROLES:
        return "Error: your role does not have access to this data."
    conn = _conn(db_name, db_server, db_user, db_password)
    if not conn:
        return "Error: could not connect to the hospital database."
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM tblIpBedsDtl WHERE isPresent = 1")
        occupied = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM tblIpBeds WHERE ACTIVE = 1")
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
    try:
        date_from, date_to, label = _period_dates(q)
    except _UnrecognizedPeriod:
        return None

    conn = _conn(db_name, db_server, db_user, db_password)
    if not conn:
        return "Error: could not connect to the hospital database."
    try:
        cursor = conn.cursor()
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
              AND CAST(FM.REQDT AS DATE) >= ? AND CAST(FM.REQDT AS DATE) < ?
            ORDER BY FM.REQDT DESC
        """, (date_from, date_to))
        rows = cursor.fetchall()
        if not rows:
            return f"No investigations ordered ({label}, OP)."

        return _list_card(
            icon="🧪", title="Investigations Ordered (OP)", intro=f"{label} — {len(rows)} shown:",
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
    try:
        date_from, date_to, label = _period_dates(q)
    except _UnrecognizedPeriod:
        return None

    conn = _conn(db_name, db_server, db_user, db_password)
    if not conn:
        return "Error: could not connect to the hospital database."
    try:
        cursor = conn.cursor()
        lcode, loc_name = _resolve_location(q, cursor)
        loc_sql = " AND LCODE = ?" if lcode else ""

        params1 = (date_from, date_to, lcode) if lcode else (date_from, date_to)
        cursor.execute(f"""
            SELECT
                SUM(CASE WHEN TTYPE = 4 THEN AMTPAID ELSE 0 END) AS Registration,
                SUM(CASE WHEN TTYPE = 3 THEN AMTPAID ELSE 0 END) AS Services,
                SUM(CASE WHEN TTYPE = 2 THEN AMTPAID ELSE 0 END) AS Operations,
                SUM(AMTPAID) AS TOTAL
            FROM tblOPPAYDTLS
            WHERE CAST(DTPAID AS DATE) >= ? AND CAST(DTPAID AS DATE) < ? AND TTYPE IN (2, 3, 4){loc_sql}
        """, params1)
        reg, services, ops, op_total = (float(x or 0) for x in cursor.fetchone())

        loc_sql_p = " AND P.LCODE = ?" if lcode else ""
        params2 = (date_from, date_to, lcode) if lcode else (date_from, date_to)
        cursor.execute(f"""
            SELECT ISNULL(SUM(P.AMTPAID), 0)
            FROM tblOPPAYDTLS P
            INNER JOIN tblOPRegistration R ON R.Billno = P.BILLNO AND R.TTYPE = P.TTYPE
            WHERE CAST(P.DTPAID AS DATE) >= ? AND CAST(P.DTPAID AS DATE) < ? AND R.TTYPE = 0 AND R.Cancelled = 'False'{loc_sql_p}
        """, params2)
        consultation = float(cursor.fetchone()[0] or 0)

        loc_sql_pd = " AND PD.LCODE = ?" if lcode else ""
        params3 = (date_from, date_to, lcode) if lcode else (date_from, date_to)
        cursor.execute(f"""
            SELECT ISNULL(SUM(PD.AMTPAID), 0)
            FROM tblPATREQPYMTDET PD
            INNER JOIN tblPatReqHdr H ON H.REQDT = PD.REQDT AND H.REQNO = PD.REQNO
            WHERE CAST(PD.DTPAID AS DATE) >= ? AND CAST(PD.DTPAID AS DATE) < ? AND H.CAN_FLG = 'N'{loc_sql_pd}
        """, params3)
        oplab = float(cursor.fetchone()[0] or 0)

        grand_total = op_total + consultation + oplab
        subtitle = f"{label}" + (f" · {loc_name}" if loc_name else " · All Branches")

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
    try:
        date_from, date_to, label = _period_dates(q)
    except _UnrecognizedPeriod:
        return None

    conn = _conn(db_name, db_server, db_user, db_password)
    if not conn:
        return "Error: could not connect to the hospital database."
    try:
        cursor = conn.cursor()
        lcode, loc_name = _resolve_location(q, cursor)
        loc_sql = " AND LCODE = ?" if lcode else ""

        p1 = (date_from, date_to, lcode) if lcode else (date_from, date_to)
        cursor.execute(f"""
            SELECT ISNULL(SUM(PAIDAMT), 0)
            FROM tblIPAdvances WHERE CAST(BILLDT AS DATE) >= ? AND CAST(BILLDT AS DATE) < ? AND TTYPE = 0{loc_sql}
        """, p1)
        advance = float(cursor.fetchone()[0] or 0)

        p2 = (date_from, date_to, lcode) if lcode else (date_from, date_to)
        cursor.execute(f"""
            SELECT ISNULL(SUM(AMTPAID), 0)
            FROM tblIPPAYDTLS WHERE CAST(DTPAID AS DATE) >= ? AND CAST(DTPAID AS DATE) < ? AND TTYPE = 21{loc_sql}
        """, p2)
        final_cash = float(cursor.fetchone()[0] or 0)

        p3 = (date_from, date_to, lcode) if lcode else (date_from, date_to)
        cursor.execute(f"""
            SELECT ISNULL(SUM(AMTPAID), 0)
            FROM tblIPCORPPAYDTLS WHERE CAST(DTPAID AS DATE) >= ? AND CAST(DTPAID AS DATE) < ? AND TTYPE = 25{loc_sql}
        """, p3)
        final_corp = float(cursor.fetchone()[0] or 0)

        total = advance + final_cash + final_corp
        subtitle = f"{label}" + (f" · {loc_name}" if loc_name else " · All Branches")

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
            icon="🧪", title="Investigation Catalog", intro=f"{len(rows)} shown:",
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
    m = re.search(r"(?:find|search|lookup)\s+patient\s+([a-zA-Z ]+)", q)
    if not m:
        return None
    name_search = m.group(1).strip()

    conn = _conn(db_name, db_server, db_user, db_password)
    if not conn:
        return "Error: could not connect to the hospital database."
    try:
        cursor = conn.cursor()
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
            icon="🧑‍🤝‍🧑", title="Patient Search", intro=f"Matching '{name_search}':",
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
    try:
        date_from, date_to, label = _period_dates(q)
    except _UnrecognizedPeriod:
        return None

    conn = _conn(db_name, db_server, db_user, db_password)
    if not conn:
        return "Error: could not connect to the hospital database."
    try:
        cursor = conn.cursor()
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
              AND IP.REGDT >= ? AND IP.REGDT < ?
            ORDER BY doc.DocName, IP.REGDT
        """, (date_from, date_to))
        rows = cursor.fetchall()
        if not rows:
            return f"No equipment usage recorded for discharged patients ({label})."
        return _list_card(
            icon="🩺", title="Equipment Usage", intro=f"{label} — {len(rows)} shown:",
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
    try:
        date_from, date_to, label = _period_dates(q)
    except _UnrecognizedPeriod:
        return None

    conn = _conn(db_name, db_server, db_user, db_password)
    if not conn:
        return "Error: could not connect to the hospital database."
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT TOP 15 A.PatientName, D.DocName, A.FromTime, A.ToTime, A.MobileNumber
            FROM tblDocAppointments A
            LEFT JOIN tblDoctorInfo D ON D.DocId = A.DocId
            WHERE CAST(A.AppointDt AS DATE) >= ? AND CAST(A.AppointDt AS DATE) < ?
            ORDER BY A.FromTime
        """, (date_from, date_to))
        rows = cursor.fetchall()
        if not rows:
            return f"No appointments found for {label}."
        return _list_card(
            icon="📅", title="Appointments", intro=f"{label} — {len(rows)} shown:",
            items=[
                {"primary": pat, "fields": [f"Dr. {doc or 'Unknown'}", f"{ft}–{tt}", f"Ph: {mob}" if mob else "Ph: -"]}
                for pat, doc, ft, tt, mob in rows
            ],
        )
    except Exception as e:
        return f"Error: {e}"
    finally:
        conn.close()


# ---------- low_stock (real, corrected — sums CURRQTY across all batches
# per medicine before comparing to reorder level; confirmed via SSMS
# that individual batches often show near-zero while the real SUMMED
# total is genuinely non-zero — comparing per-batch was a real bug) ----------
def _handle_low_stock(q, role, db_name, db_server, db_user, db_password, matched_keyword=None):
    if role not in _ALLOWED_ROLES:
        return "Error: your role does not have access to this data."
    conn = _conn(db_name, db_server, db_user, db_password)
    if not conn:
        return "Error: could not connect to the hospital database."
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT TOP 15 M.MEDNM, SUM(D.CURRQTY) AS TotalQty, M.ROL
            FROM tblPharmDeptMedDtls D
            INNER JOIN tblPharmMedicines M ON M.MEDID = D.MEDID
            GROUP BY M.MEDID, M.MEDNM, M.ROL
            HAVING SUM(D.CURRQTY) < M.ROL
            ORDER BY (M.ROL - SUM(D.CURRQTY)) DESC
        """)
        rows = cursor.fetchall()
        if not rows:
            return "No items currently below their reorder level."
        return _list_card(
            icon="💊", title="Low Stock Items (Below Reorder Level)",
            intro=f"{len(rows)} shown (summed across all batches):",
            items=[
                {"primary": name, "fields": [f"Total Current: {int(qty or 0)}", f"Reorder Level: {int(rol or 0)}"]}
                for name, qty, rol in rows
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
    try:
        date_from, date_to, label = _period_dates(q)
    except _UnrecognizedPeriod:
        return None

    conn = _conn(db_name, db_server, db_user, db_password)
    if not conn:
        return "Error: could not connect to the hospital database."
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 'Debit' AS VoucherType, V.VoucherNo, AC.AccountHeaderNAME, -Amount AS Amount, Remarks
            FROM tblVoucherGeneration V
            INNER JOIN tblAccountHeader AC ON AC.AccountHeaderID = V.AccHeaderId
            WHERE V.VoucherType = 0 AND CAST(V.VoucherDt AS DATE) >= ? AND CAST(V.VoucherDt AS DATE) < ?
            UNION ALL
            SELECT 'Credit' AS VoucherType, V.VoucherNo, AC.AccountHeaderNAME, Amount, Remarks
            FROM tblVoucherGeneration V
            INNER JOIN tblAccountHeader AC ON AC.AccountHeaderID = V.AccHeaderId
            WHERE V.VoucherType = 1 AND CAST(V.VoucherDt AS DATE) >= ? AND CAST(V.VoucherDt AS DATE) < ?
        """, (date_from, date_to, date_from, date_to))
        rows = cursor.fetchall()
        if not rows:
            return f"No expenditure vouchers recorded ({label})."

        total = sum(float(amt or 0) for _, _, _, amt, _ in rows)
        return _list_card(
            icon="🧾", title="Expenditure Vouchers", intro=f"{label} — Net: ₹{total:,.0f} ({len(rows)} entries):",
            items=[
                {"primary": f"{vtype} · {header}", "fields": [f"Voucher #{vno}", f"₹{float(amt or 0):,.0f}", remarks or "-"]}
                for vtype, vno, header, amt, remarks in rows[:15]
            ],
        )
    except Exception as e:
        return f"Error: {e}"
    finally:
        conn.close()


# ---------- compare_op_ip_revenue (real — calls both handlers, combines results) ----------
def _handle_compare_op_ip(q, role, db_name, db_server, db_user, db_password, matched_keyword=None):
    if role not in _ALLOWED_ROLES:
        return "Error: your role does not have access to this data."
    if "op" not in q or "ip" not in q:
        return None  # not genuinely a compare question, fall through

    op_result = _handle_op_revenue(q, role, db_name, db_server, db_user, db_password)
    ip_result = _handle_ip_revenue(q, role, db_name, db_server, db_user, db_password)
    if not op_result or not ip_result:
        return None
    return op_result + "\n\n" + ip_result


# ---------- total_hospital_revenue (real — combines OP + IP + Pharmacy + Lab) ----------
def _handle_total_revenue(q, role, db_name, db_server, db_user, db_password, matched_keyword=None):
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

        # OP — same 3 real queries op_revenue uses, reused inline
        cursor.execute("""
            SELECT SUM(AMTPAID) FROM tblOPPAYDTLS
            WHERE CAST(DTPAID AS DATE) >= ? AND CAST(DTPAID AS DATE) < ? AND TTYPE IN (2, 3, 4)
        """, (date_from, date_to))
        op_base = float(cursor.fetchone()[0] or 0)

        cursor.execute("""
            SELECT ISNULL(SUM(P.AMTPAID), 0)
            FROM tblOPPAYDTLS P
            INNER JOIN tblOPRegistration R ON R.Billno = P.BILLNO AND R.TTYPE = P.TTYPE
            WHERE CAST(P.DTPAID AS DATE) >= ? AND CAST(P.DTPAID AS DATE) < ? AND R.TTYPE = 0 AND R.Cancelled = 'False'
        """, (date_from, date_to))
        consultation = float(cursor.fetchone()[0] or 0)

        cursor.execute("""
            SELECT ISNULL(SUM(PD.AMTPAID), 0)
            FROM tblPATREQPYMTDET PD
            INNER JOIN tblPatReqHdr H ON H.REQDT = PD.REQDT AND H.REQNO = PD.REQNO
            WHERE CAST(PD.DTPAID AS DATE) >= ? AND CAST(PD.DTPAID AS DATE) < ? AND H.CAN_FLG = 'N'
        """, (date_from, date_to))
        oplab = float(cursor.fetchone()[0] or 0)
        op_total = op_base + consultation + oplab

        # IP — same 3 real queries ip_revenue uses
        cursor.execute("""
            SELECT ISNULL(SUM(PAIDAMT), 0) FROM tblIPAdvances
            WHERE CAST(BILLDT AS DATE) >= ? AND CAST(BILLDT AS DATE) < ? AND TTYPE = 0
        """, (date_from, date_to))
        ip_advance = float(cursor.fetchone()[0] or 0)

        cursor.execute("""
            SELECT ISNULL(SUM(AMTPAID), 0) FROM tblIPPAYDTLS
            WHERE CAST(DTPAID AS DATE) >= ? AND CAST(DTPAID AS DATE) < ? AND TTYPE = 21
        """, (date_from, date_to))
        ip_cash = float(cursor.fetchone()[0] or 0)

        cursor.execute("""
            SELECT ISNULL(SUM(AMTPAID), 0) FROM tblIPCORPPAYDTLS
            WHERE CAST(DTPAID AS DATE) >= ? AND CAST(DTPAID AS DATE) < ? AND TTYPE = 25
        """, (date_from, date_to))
        ip_corp = float(cursor.fetchone()[0] or 0)
        ip_total = ip_advance + ip_cash + ip_corp

        # Pharmacy — REAL table (tblPharmAmountTrans) confirmed by AthenTech
        # devs to exist and be keyed on BILLDT, but its exact payment
        # column name was NEVER verified via SSMS (unlike every other
        # query in this file). Guessing AMOUNTPAID based on the pattern
        # seen elsewhere (tblIPAMTTRANS.AMOUNTPAID). VERIFY before
        # trusting this number specifically.
        pharmacy_total = 0.0
        pharmacy_note = ""
        try:
            cursor.execute("""
                SELECT ISNULL(SUM(AMOUNTPAID), 0) FROM tblPharmAmountTrans
                WHERE CAST(BILLDT AS DATE) >= ? AND CAST(BILLDT AS DATE) < ?
            """, (date_from, date_to))
            pharmacy_total = float(cursor.fetchone()[0] or 0)
        except Exception as pharm_err:
            pharmacy_note = f" (pharmacy figure unavailable — unverified column: {pharm_err})"

        grand_total = op_total + ip_total + pharmacy_total

        return _dashboard_card(
            icon="🏥", title="Total Hospital Revenue", subtitle=label + pharmacy_note,
            stats=[
                {"label": "GRAND TOTAL", "value": f"₹{grand_total:,.0f}"},
                {"label": "OP", "value": f"₹{op_total:,.0f}"},
                {"label": "IP", "value": f"₹{ip_total:,.0f}"},
                {"label": "PHARMACY", "value": f"₹{pharmacy_total:,.0f}"},
            ],
        )
    except Exception as e:
        return f"Error: {e}"
    finally:
        conn.close()


# ---------- doctor_wise_revenue (real — consultations + revenue per doctor) ----------
def _handle_doctor_wise_revenue(q, role, db_name, db_server, db_user, db_password, matched_keyword=None):
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
        cursor.execute("""
            SELECT TOP 10 D.DocName, COUNT(*) AS Consultations, SUM(P.AMTPAID) AS Revenue
            FROM tblOPRegistration R
            INNER JOIN tblDoctorInfo D ON D.DocId = R.DocId
            INNER JOIN tblOPPAYDTLS P ON P.BILLNO = R.Billno AND P.TTYPE = R.TTYPE
            WHERE R.TTYPE = 0 AND R.Cancelled = 'False'
              AND CAST(P.DTPAID AS DATE) >= ? AND CAST(P.DTPAID AS DATE) < ?
            GROUP BY D.DocName
            ORDER BY SUM(P.AMTPAID) DESC
        """, (date_from, date_to))
        rows = cursor.fetchall()
        if not rows:
            return f"No doctor-wise consultation data found ({label})."
        return _list_card(
            icon="👨‍⚕️", title="Doctor-Wise Consultations & Revenue", intro=f"{label} — top 10:",
            items=[
                {"primary": doc, "fields": [f"{int(count)} consultations", f"₹{float(rev or 0):,.0f}"]}
                for doc, count, rev in rows
            ],
        )
    except Exception as e:
        return f"Error: {e}"
    finally:
        conn.close()


# ---------- discharge_summary (real — from confirmed tblIPDischSummary, seen joined
# to tblIPFinalBillMst in AthenTech's own R_DAILYAUDIT stored procedure) ----------
def _handle_discharge_summary(q, role, db_name, db_server, db_user, db_password, matched_keyword=None):
    if role not in _ALLOWED_ROLES:
        return "Error: your role does not have access to this data."
    m = re.search(r"\b([A-Za-z]{2,6}\d{3,})\b", q.upper())
    if not m:
        return None
    identifier = m.group(1)

    conn = _conn(db_name, db_server, db_user, db_password)
    if not conn:
        return "Error: could not connect to the hospital database."
    try:
        cursor = conn.cursor()
        # tblIPDischSummary's exact columns beyond IPNO were never
        # verified via SSMS — this is built from its confirmed EXISTENCE
        # and join key (seen in AthenTech's real R_DAILYAUDIT SP), not
        # a confirmed column list. SELECT * to avoid guessing wrong names.
        cursor.execute("""
            SELECT TOP 1 *
            FROM tblIPDischSummary
            WHERE IPNO = ?
        """, (identifier,))
        row = cursor.fetchone()
        if not row:
            return f"No discharge summary found for '{identifier}'."
        col_names = [d[0] for d in cursor.description]
        record = dict(zip(col_names, row))
        return _list_card(
            icon="📋", title=f"Discharge Summary · {identifier}",
            items=[{"primary": k, "fields": [str(v)]} for k, v in record.items() if v not in (None, "")][:15],
        )
    except Exception as e:
        return f"Error: {e} (tblIPDischSummary's real columns were never verified — this table's existence is confirmed, but its schema is a guess)"
    finally:
        conn.close()


_INTENTS_HIS = [
    (["total hospital revenue", "combined revenue", "overall revenue", "total revenue"],
     _handle_total_revenue),
    (["doctor wise revenue", "doctor-wise revenue", "doctor collection", "consultations by doctor",
      "doctor wise consultation"], _handle_doctor_wise_revenue),
    (["discharge summary"], _handle_discharge_summary),
    (["compare op", "op vs ip", "ip vs op", "compare ip"], _handle_compare_op_ip),
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
      "collection this month", "collection this year", "total collection", "collection 20"],
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


# Handlers that genuinely support location filtering — everything else
# should NOT silently answer a location-scoped question as if it were
# unscoped. Add a handler here only once it actually applies the
# resolved LCODE to its query.
_LOCATION_AWARE_HANDLERS = {_handle_op_revenue, _handle_ip_revenue}


def try_intent_his(question, role, db_name, db_server=None, db_user=None, db_password=None):
    q = (question or "").strip().lower()
    for keywords, handler in _INTENTS_HIS:
        matched = next((kw for kw in keywords if kw in q), None)
        if not matched:
            continue

        # Real safety check: if the question names a location but the
        # matched handler doesn't actually use one, don't silently
        # answer as if unscoped — that's a wrong answer, not a right
        # one with a missing filter. Fall through to the next intent
        # (and eventually the LLM) instead.
        if handler not in _LOCATION_AWARE_HANDLERS:
            conn = get_hospital_connection(db_name, db_server, db_user, db_password)
            if conn:
                try:
                    cursor = conn.cursor()
                    lcode, loc_name = _resolve_location(q, cursor)
                    if lcode:
                        continue  # a real location was named, this handler can't honor it — skip it
                finally:
                    conn.close()

        try:
            result = handler(q, role, db_name, db_server, db_user, db_password, matched_keyword=matched)
        except _UnrecognizedPeriod:
            continue
        if result is not None:
            return result
    return None