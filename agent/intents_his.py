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


_INTENTS_HIS = [
    (["beds occupied", "bed occupancy", "occupied beds", "beds are occupied",
      "how many beds", "bed status", "beds available", "available beds"],
     _handle_bed_occupancy_count),
    (["currently admitted", "admitted patients", "who is admitted", "patients admitted",
      "who's admitted"],
     _handle_currently_admitted),
    (["admission for", "admission details", "admitted uhid", "ipno"], _handle_admission_lookup),
]


def try_intent_his(question: str, role: str, db_name: str, db_server=None, db_user=None, db_password=None):
    """
    Returns an answer string (dashboard-card/list-card JSON, or a plain
    error/no-data string) if a fixed-SQL HIS intent matched, or None to
    fall through to the "still being built" placeholder in ask_agent.
    """
    q = (question or "").strip().lower()
    for keywords, handler in _INTENTS_HIS:
        matched = next((kw for kw in keywords if kw in q), None)
        if matched:
            result = handler(q, role, db_name, db_server, db_user, db_password, matched_keyword=matched)
            if result is not None:
                return result
    return None