"""
Intent dispatcher — keyword-matched questions get answered with FIXED,
verified SQL and proper dashboard-card/list-card JSON output, no LLM
call at all (zero token cost). Falls through to the normal LLM path
(returns None) if no intent matches or a handler can't confidently answer.
"""

import json
import re
from datetime import date, timedelta

from database.connection import get_hospital_connection

_ALLOWED_ROLES = ("admin", "doctor", "reception")


def _period_dates(q: str):
    today = date.today()
    if "yesterday" in q:
        d = today - timedelta(days=1)
        return d.isoformat(), (d + timedelta(days=1)).isoformat(), "Yesterday"
    if "this month" in q:
        start = today.replace(day=1)
        return start.isoformat(), (today + timedelta(days=1)).isoformat(), "This Month"
    return today.isoformat(), (today + timedelta(days=1)).isoformat(), "Today"


def _conn(db_name, db_server, db_user, db_password):
    return get_hospital_connection(db_name, db_server, db_user, db_password)


def _dashboard_card(**kwargs) -> str:
    return "```dashboard-card\n" + json.dumps(kwargs) + "\n```"


def _list_card(**kwargs) -> str:
    return "```list-card\n" + json.dumps(kwargs) + "\n```"


# ---------- all_collection ----------
def _handle_all_collection(q, role, db_name, db_server, db_user, db_password):
    if role not in _ALLOWED_ROLES:
        return "Error: your role does not have access to this data."
    date_from, date_to, label = _period_dates(q)
    conn = _conn(db_name, db_server, db_user, db_password)
    if not conn:
        return "Error: could not connect to the database."
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT UPPER(LTRIM(RTRIM(MODE))) AS MODE, SUM(PAIDAMOUNT) AS Amt "
            "FROM trnmodeofcollectionsdet "
            "WHERE DATEOFBILL >= ? AND DATEOFBILL < ? GROUP BY UPPER(LTRIM(RTRIM(MODE)))",
            (date_from, date_to),
        )
        rows = cursor.fetchall()
        if not rows:
            return f"No collection records found for {label} across all branches."
        total = sum(float(r[1] or 0) for r in rows)
        rows_sorted = sorted(rows, key=lambda r: -(r[1] or 0))
        return _dashboard_card(
            icon="💰", title="All-Branches Collection", subtitle=label,
            stats=[{"label": "TOTAL", "value": f"₹{total:,.0f}"}],
            bar_section={
                "title": "By Payment Mode", "subtitle": "(amount · %)",
                "rows": [
                    {"label": m.title(), "value": float(amt or 0),
                     "extra": f"₹{float(amt or 0):,.0f} ({float(amt or 0)/total*100:.0f}%)" if total else "₹0"}
                    for m, amt in rows_sorted
                ],
            },
        )
    except Exception as e:
        return f"Error: {e}"
    finally:
        conn.close()


# ---------- patients_count ----------
def _handle_patients_count(q, role, db_name, db_server, db_user, db_password):
    if role not in _ALLOWED_ROLES:
        return "Error: your role does not have access to this data."
    date_from, date_to, label = _period_dates(q)
    conn = _conn(db_name, db_server, db_user, db_password)
    if not conn:
        return "Error: could not connect to the database."
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM mstpatientregistration WHERE REGDATE >= ? AND REGDATE < ?",
            (date_from, date_to),
        )
        count = cursor.fetchone()[0]
        return _dashboard_card(
            icon="🧑‍🤝‍🧑", title="Patients Registered", subtitle=label,
            stats=[{"label": "COUNT", "value": f"{count:,}"}],
        )
    except Exception as e:
        return f"Error: {e}"
    finally:
        conn.close()


# ---------- uhid_lookup ----------
def _handle_uhid_lookup(q, role, db_name, db_server, db_user, db_password):
    if role not in _ALLOWED_ROLES:
        return "Error: your role does not have access to this data."
    m = re.search(r"\b([A-Za-z]{2,4}\d{4,})\b", q.upper())
    if not m:
        return None
    uhid = m.group(1)
    conn = _conn(db_name, db_server, db_user, db_password)
    if not conn:
        return "Error: could not connect to the database."
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT NAME, UHID, PHONENO, REGDATE FROM mstpatientregistration WHERE UHID = ?",
            (uhid,),
        )
        row = cursor.fetchone()
        if not row:
            return f"No patient found with UHID {uhid}."
        return _list_card(
            icon="🧑‍🤝‍🧑", title="Patient Found",
            items=[{"primary": row[0], "fields": [f"UHID: {row[1]}", f"Phone: {row[2]}", f"Registered: {row[3]}"]}],
        )
    except Exception as e:
        return f"Error: {e}"
    finally:
        conn.close()


# ---------- test_lookup ----------
def _handle_test_lookup(q, role, db_name, db_server, db_user, db_password):
    if role not in _ALLOWED_ROLES:
        return "Error: your role does not have access to this data."
    m = re.search(r"(?:lookup|list|what is)\s+(.+)", q)
    term = m.group(1).strip() if m else None
    if not term or len(term) < 2:
        return None
    conn = _conn(db_name, db_server, db_user, db_password)
    if not conn:
        return "Error: could not connect to the database."
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT TOP 10 INVNAME, RATE FROM mstInvestigations WHERE INVNAME LIKE ?",
            (f"%{term}%",),
        )
        rows = cursor.fetchall()
        if not rows:
            return None
        return _list_card(
            icon="🧪", title=f"Tests matching '{term}'",
            items=[
                {"primary": name, "fields": [f"Rate: ₹{rate:,.0f}"] if rate else []}
                for name, rate in rows
            ],
        )
    except Exception as e:
        return f"Error: {e}"
    finally:
        conn.close()


# ---------- locations_list ----------
def _handle_locations_list(q, role, db_name, db_server, db_user, db_password):
    if role not in _ALLOWED_ROLES:
        return "Error: your role does not have access to this data."
    conn = _conn(db_name, db_server, db_user, db_password)
    if not conn:
        return "Error: could not connect to the database."
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT LOCATIONID, LOCATIONNAME FROM mstlocation WHERE ACTIVE = 1 ORDER BY LOCATIONNAME")
        rows = cursor.fetchall()
        if not rows:
            return "No active locations found."
        return _list_card(
            icon="📍", title=f"Active Branches ({len(rows)})",
            items=[{"primary": name, "fields": [f"Code: {loc_id}"]} for loc_id, name in rows],
        )
    except Exception as e:
        return f"Error: {e}"
    finally:
        conn.close()


# ---------- referring_doctors ----------
def _handle_referring_doctors(q, role, db_name, db_server, db_user, db_password):
    if role not in _ALLOWED_ROLES:
        return "Error: your role does not have access to this data."
    date_from, date_to, label = _period_dates(q)
    if "today" not in q and "yesterday" not in q:
        today = date.today()
        date_from, date_to, label = today.replace(day=1).isoformat(), (today + timedelta(days=1)).isoformat(), "This Month"
    by_revenue = "revenue" in q
    conn = _conn(db_name, db_server, db_user, db_password)
    if not conn:
        return "Error: could not connect to the database."
    try:
        cursor = conn.cursor()
        if by_revenue:
            cursor.execute(
                "SELECT TOP 10 d.DOCNAME, SUM(p.PAIDAMOUNT) AS Amt FROM trninvlabpri p "
                "JOIN mstrefdoctor d ON p.REFDOCTCODE = d.DOCID "
                "WHERE p.BILLDATE >= ? AND p.BILLDATE < ? GROUP BY d.DOCNAME ORDER BY Amt DESC",
                (date_from, date_to),
            )
        else:
            cursor.execute(
                "SELECT TOP 10 d.DOCNAME, COUNT(p.BILLNO) AS Cnt FROM trninvlabpri p "
                "JOIN mstrefdoctor d ON p.REFDOCTCODE = d.DOCID "
                "WHERE p.BILLDATE >= ? AND p.BILLDATE < ? GROUP BY d.DOCNAME ORDER BY Cnt DESC",
                (date_from, date_to),
            )
        rows = cursor.fetchall()
        if not rows:
            return f"No referring doctor data found for {label}."
        return _list_card(
            icon="👨‍⚕️", title=f"Top Referring Doctors · {label}",
            items=[
                {"primary": name, "fields": [f"₹{float(val or 0):,.0f}" if by_revenue else f"{val} bills"]}
                for name, val in rows
            ],
        )
    except Exception as e:
        return f"Error: {e}"
    finally:
        conn.close()


# ---------- bill_detail ----------
def _handle_bill_detail(q, role, db_name, db_server, db_user, db_password):
    if role not in _ALLOWED_ROLES:
        return "Error: your role does not have access to this data."
    m = re.search(r"\bbill\s*(?:no\.?|number)?\s*[:\-]?\s*([A-Za-z0-9]{4,})", q, re.IGNORECASE)
    if not m:
        return None
    billno = m.group(1).upper()
    conn = _conn(db_name, db_server, db_user, db_password)
    if not conn:
        return "Error: could not connect to the database."
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT b.Name, b.Phone, c.INVNAME, p.PARAMHEADNAME, p.PVALUE, p.MINVALUE, p.MAXVALUE "
            "FROM trnINVLABDET a "
            "JOIN trnINVLABPRI b ON a.BILLNO = b.BILLNO "
            "JOIN mstInvestigations c ON a.TCODE = c.INVCODE "
            "JOIN trnParamResult p ON a.BILLNO = p.BILLNO "
            "WHERE a.BILLNO = ?",
            (billno,),
        )
        rows = cursor.fetchall()
        if not rows:
            return f"No records found for bill {billno}."
        name, phone = rows[0][0], rows[0][1]
        items = []
        for _, _, inv, param, pval, minv, maxv in rows[:15]:
            fields = [f"Value: {pval}"]
            if minv is not None and maxv is not None:
                fields.append(f"Range: {minv}-{maxv}")
            items.append({"primary": f"{inv} — {param}" if param else inv, "fields": fields})
        return _list_card(
            icon="🧾", title=f"Bill {billno}", intro=f"{name} · {phone}",
            items=items,
        )
    except Exception as e:
        return f"Error: {e}"
    finally:
        conn.close()


# ---------- departments_list ----------
def _handle_departments_list(q, role, db_name, db_server, db_user, db_password):
    if role not in _ALLOWED_ROLES:
        return "Error: your role does not have access to this data."
    conn = _conn(db_name, db_server, db_user, db_password)
    if not conn:
        return "Error: could not connect to the database."
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT SubDeptName FROM mstsubdepartment WHERE IsBranch = 1 ORDER BY SubDeptName")
        rows = cursor.fetchall()
        if not rows:
            return "No departments found."
        return _list_card(
            icon="🏥", title=f"Departments ({len(rows)})",
            items=[{"primary": r[0]} for r in rows],
        )
    except Exception as e:
        return f"Error: {e}"
    finally:
        conn.close()


_INTENTS = [
    (["all branches collection", "total collection", "total paidamount",
      "collection by payment mode", "upi total"], _handle_all_collection),
    (["patients registered", "how many patients"], _handle_patients_count),
    (["uhid"], _handle_uhid_lookup),
    (["lookup cbp", "what is cue", "complete urine analysis", "list urine tests",
      "list blood tests"], _handle_test_lookup),
    (["active locations", "how many branches", "list all locations",
      "list all branches"], _handle_locations_list),
    (["referring doctors", "top doctors", "top 10 referring"], _handle_referring_doctors),
    (["bill no", "bill number", "bill "], _handle_bill_detail),
    (["list departments", "list all departments", "which departments"], _handle_departments_list),
]


def try_intent(question: str, role: str, db_name: str, db_server=None, db_user=None, db_password=None):
    """
    Returns an answer string (dashboard-card/list-card JSON, or a plain
    'no data'/'error' string) if a fixed-SQL intent matched and
    confidently answered, or None to fall through to the normal LLM path.
    """
    q = (question or "").strip().lower()
    for keywords, handler in _INTENTS:
        if any(kw in q for kw in keywords):
            result = handler(q, role, db_name, db_server, db_user, db_password)
            if result is not None:
                return result
    return None