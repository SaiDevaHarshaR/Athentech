"""
Intent dispatcher — keyword-matched questions get answered with FIXED,
verified SQL, no LLM call at all (zero token cost). Falls through to
the normal LLM path if no intent matches or if the handler can't
confidently answer.

Each intent: (keywords, handler). Handler takes (question_lower, role,
db_name, db_server, db_user, db_password) and returns a formatted
answer string, or None to fall through to the LLM.
"""

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
        return start.isoformat(), today.isoformat(), "This Month"
    # default: today
    return today.isoformat(), (today + timedelta(days=1)).isoformat(), "Today"


def _conn(db_name, db_server, db_user, db_password):
    return get_hospital_connection(db_name, db_server, db_user, db_password)


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
        lines = [f"💰 **All-Branches Collection** · {label}", f"**Total:** ₹{total:,.0f}", ""]
        for mode, amt in sorted(rows, key=lambda r: -(r[1] or 0)):
            pct = (float(amt or 0) / total * 100) if total else 0
            lines.append(f"• **{mode.title()}:** ₹{float(amt or 0):,.0f} ({pct:.0f}%)")
        return "\n".join(lines)
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
        return f"🧑‍🤝‍🧑 **Patients Registered** · {label}\n**Count:** {count:,}"
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
        return None  # can't confidently extract a UHID, let the LLM handle it
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
        return f"🧑‍🤝‍🧑 **Patient Found**\n**Name:** {row[0]} · **UHID:** {row[1]} · **Phone:** {row[2]} · **Registered:** {row[3]}"
    except Exception as e:
        return f"Error: {e}"
    finally:
        conn.close()


# ---------- test_lookup ----------
def _handle_test_lookup(q, role, db_name, db_server, db_user, db_password):
    if role not in _ALLOWED_ROLES:
        return "Error: your role does not have access to this data."
    # Extract the term after common lookup phrasing; falls through if unclear
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
            return None  # let the LLM try broader matching per the confirmed lay-name pattern
        lines = [f"🧪 **Tests matching '{term}'**"]
        for name, rate in rows:
            lines.append(f"• {name} — ₹{rate:,.0f}" if rate else f"• {name}")
        return "\n".join(lines)
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
        lines = [f"📍 **Active Branches** ({len(rows)})"]
        for loc_id, name in rows:
            lines.append(f"• {name} ({loc_id})")
        return "\n".join(lines)
    except Exception as e:
        return f"Error: {e}"
    finally:
        conn.close()


# ---------- referring_doctors ----------
def _handle_referring_doctors(q, role, db_name, db_server, db_user, db_password):
    if role not in _ALLOWED_ROLES:
        return "Error: your role does not have access to this data."
    date_from, date_to, label = _period_dates(q)
    if "this month" not in q and "today" not in q and "yesterday" not in q:
        # default to this month for a "top doctors" style question with no period
        today = date.today()
        date_from, date_to, label = today.replace(day=1).isoformat(), today.isoformat(), "This Month"
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
        lines = [f"👨‍⚕️ **Top Referring Doctors** · {label}"]
        for i, (name, val) in enumerate(rows, 1):
            val_str = f"₹{float(val or 0):,.0f}" if by_revenue else f"{val} bills"
            lines.append(f"{i}. {name} — {val_str}")
        return "\n".join(lines)
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
]


def try_intent(question: str, role: str, db_name: str, db_server=None, db_user=None, db_password=None):
    """
    Returns an answer string if a fixed-SQL intent matched and confidently
    answered, or None to fall through to the normal LLM path.
    """
    q = (question or "").strip().lower()
    for keywords, handler in _INTENTS:
        if any(kw in q for kw in keywords):
            result = handler(q, role, db_name, db_server, db_user, db_password)
            if result is not None:
                return result
    return None