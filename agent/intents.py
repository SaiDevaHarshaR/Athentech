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
    q = q.lower()

    if "yesterday" in q:
        d = today - timedelta(days=1)
        return d.isoformat(), (d + timedelta(days=1)).isoformat(), "Yesterday"
    if "last week" in q:
        # Monday-start previous week
        start = today - timedelta(days=today.weekday() + 7)
        end = start + timedelta(days=7)
        return start.isoformat(), end.isoformat(), "Last Week"
    if "this week" in q:
        start = today - timedelta(days=today.weekday())
        return start.isoformat(), (today + timedelta(days=1)).isoformat(), "This Week"
    if "last month" in q:
        first_this = today.replace(day=1)
        last_month_end = first_this
        last_month_start = (first_this - timedelta(days=1)).replace(day=1)
        return last_month_start.isoformat(), last_month_end.isoformat(), "Last Month"
    if "this month" in q:
        start = today.replace(day=1)
        return start.isoformat(), (today + timedelta(days=1)).isoformat(), "This Month"
    if "this year" in q:
        start = today.replace(month=1, day=1)
        return start.isoformat(), (today + timedelta(days=1)).isoformat(), "This Year"
    m = re.search(r"\b(20\d{2})-(\d{2})-(\d{2})\b", q)
    if m:
        d = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
        return d, (date.fromisoformat(d) + timedelta(days=1)).isoformat(), d
    return today.isoformat(), (today + timedelta(days=1)).isoformat(), "Today"

def _conn(db_name, db_server, db_user, db_password):
    return get_hospital_connection(db_name, db_server, db_user, db_password)


def _dashboard_card(**kwargs) -> str:
    return "```dashboard-card\n" + json.dumps(kwargs) + "\n```"


def _list_card(**kwargs) -> str:
    return "```list-card\n" + json.dumps(kwargs) + "\n```"


# ---------- all_collection ----------
def _handle_all_collection(q, role, db_name, db_server, db_user, db_password, matched_keyword=None):
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
def _handle_patients_count(q, role, db_name, db_server, db_user, db_password, matched_keyword=None):
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
def _handle_uhid_lookup(q, role, db_name, db_server, db_user, db_password, matched_keyword=None):
    if role not in _ALLOWED_ROLES:
        return "Error: your role does not have access to this data."
# Prefer explicit "UHID xxx", else a code like KDX26929648
    m = re.search(r"\buhid\s*[:\-]?\s*([A-Za-z0-9]{5,})\b", q, re.IGNORECASE)
    if not m:
        m = re.search(r"\b([A-Za-z]{2,4}\d{5,})\b", q, re.IGNORECASE)

    if not m:
        return None

    uhid = m.group(1).upper()
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
def _handle_test_lookup(q, role, db_name, db_server, db_user, db_password, matched_keyword=None):
    if role not in _ALLOWED_ROLES:
        return "Error: your role does not have access to this data."
    m = re.search(r"\bfor\s+(.+)$", q) if "master" in q or "investigation" in q else None
    if not m:
        m = re.search(r"(?:lookup|list|what is|find test)\s+(.+)", q)
    term = m.group(1).strip() if m else None
    # Strip generic wrapper words from whichever term we got — a literal
    # phrase like "blood tests" rarely matches a real INVNAME as a
    # substring; the underlying subject word ("blood") does.
    _generic = r"\b(list|lookup|tests?|investigations?|volume|today|yesterday|this week|this month)\b"
    if term:
        cleaned = re.sub(_generic, "", term).strip()
        if cleaned:
            term = cleaned
    if not term and matched_keyword:
        term = re.sub(_generic, "", matched_keyword).strip()
    if not term or len(term) < 2:
        return None
    conn = _conn(db_name, db_server, db_user, db_password)
    if not conn:
        return "Error: could not connect to the database."
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT TOP 10 INVNAME, RATE, TATTIME, TATTYPE FROM mstInvestigations WHERE INVNAME LIKE ?",
            (f"%{term}%",),
        )
        rows = cursor.fetchall()
        if not rows:
            return None
        items = []
        for name, rate, tat_time, tat_type in rows:
            fields = []
            if rate:
                fields.append(f"Rate: ₹{rate:,.0f}")
            if tat_time and tat_type:
                fields.append(f"TAT: {tat_time} {tat_type}")
            items.append({"primary": name, "fields": fields})
        return _list_card(icon="🧪", title=f"Tests matching '{term}'", items=items)
    except Exception as e:
        return f"Error: {e}"
    finally:
        conn.close()

# ---------- org_lookup ----------
def _handle_org_lookup(q, role, db_name, db_server, db_user, db_password, matched_keyword=None):
    if role not in _ALLOWED_ROLES:
        return "Error: your role does not have access to this data."
    m = re.search(r"(?:organisation|organization|client|company)\s+(.+)", q)
    term = m.group(1).strip() if m else None
    if not term or len(term) < 2:
        return None
    conn = _conn(db_name, db_server, db_user, db_password)
    if not conn:
        return "Error: could not connect to the database."
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT TOP 10 ORGANISATIONNAME, ORGANISATIONCODE, CREDITLIMIT, ACTIVE "
            "FROM mstorganisation WHERE ORGANISATIONNAME LIKE ?",
            (f"%{term}%",),
        )
        rows = cursor.fetchall()
        if not rows:
            return None
        return _list_card(
            icon="🏢", title=f"Organisations matching '{term}'",
            items=[
                {"primary": name, "fields": [f"Code: {code}", f"Credit limit: ₹{float(cl or 0):,.0f}", "Active" if act else "Inactive"]}
                for name, code, cl, act in rows
            ],
        )
    except Exception as e:
        return f"Error: {e}"
    finally:
        conn.close()


# ---------- ref_doctor_lookup ----------
def _handle_ref_doctor_lookup(q, role, db_name, db_server, db_user, db_password, matched_keyword=None):
    if role not in _ALLOWED_ROLES:
        return "Error: your role does not have access to this data."
    m = re.search(r"(?:ref doctor|referring doctor)\s+(.+)", q)
    term = m.group(1).strip() if m else None
    if not term or len(term) < 2:
        return None
    conn = _conn(db_name, db_server, db_user, db_password)
    if not conn:
        return "Error: could not connect to the database."
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT TOP 5 DOCNAME, DOCID FROM mstrefdoctor WHERE DOCNAME LIKE ?",
            (f"%{term}%",),
        )
        rows = cursor.fetchall()
        if not rows:
            return None
        return _list_card(
            icon="👨‍⚕️", title=f"Doctors matching '{term}'",
            items=[{"primary": name, "fields": [f"ID: {did}"]} for name, did in rows],
        )
    except Exception as e:
        return f"Error: {e}"
    finally:
        conn.close()


# ---------- bills_today_count ----------
def _handle_bills_count(q, role, db_name, db_server, db_user, db_password, matched_keyword=None):
    if role not in _ALLOWED_ROLES:
        return "Error: your role does not have access to this data."
    date_from, date_to, label = _period_dates(q)
    conn = _conn(db_name, db_server, db_user, db_password)
    if not conn:
        return "Error: could not connect to the database."
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(DISTINCT BILLNO) FROM trninvlabpri WHERE BILLDATE >= ? AND BILLDATE < ?",
            (date_from, date_to),
        )
        n = cursor.fetchone()[0]
        return _dashboard_card(icon="🧾", title="Bills", subtitle=label,
                                stats=[{"label": "COUNT", "value": f"{n:,}"}])
    except Exception as e:
        return f"Error: {e}"
    finally:
        conn.close()


# ---------- concession_total ----------
def _handle_concession_total(q, role, db_name, db_server, db_user, db_password, matched_keyword=None):
    if role not in _ALLOWED_ROLES:
        return "Error: your role does not have access to this data."
    date_from, date_to, label = _period_dates(q)
    conn = _conn(db_name, db_server, db_user, db_password)
    if not conn:
        return "Error: could not connect to the database."
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT SUM(CONCESSIONAMOUNT) FROM trnmodeofcollectionsdet WHERE DATEOFBILL >= ? AND DATEOFBILL < ?",
            (date_from, date_to),
        )
        total = cursor.fetchone()[0] or 0
        return _dashboard_card(icon="💰", title="Total Concession", subtitle=label,
                                stats=[{"label": "AMOUNT", "value": f"₹{float(total):,.0f}"}])
    except Exception as e:
        return f"Error: {e}"
    finally:
        conn.close()


# ---------- sample_collected_count ----------
def _handle_sample_collected_count(q, role, db_name, db_server, db_user, db_password, matched_keyword=None):
    if role not in _ALLOWED_ROLES:
        return "Error: your role does not have access to this data."
    date_from, date_to, label = _period_dates(q)
    conn = _conn(db_name, db_server, db_user, db_password)
    if not conn:
        return "Error: could not connect to the database."
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM trninvlabdet WHERE TESTSTATUS = 'Sample Collected' "
            "AND BILLDATE >= ? AND BILLDATE < ?",
            (date_from, date_to),
        )
        n = cursor.fetchone()[0]
        return _dashboard_card(icon="🧪", title="Samples Collected", subtitle=label,
                                stats=[{"label": "COUNT", "value": f"{n:,}"}])
    except Exception as e:
        return f"Error: {e}"
    finally:
        conn.close()


# ---------- authenticated_count ----------
def _handle_authenticated_count(q, role, db_name, db_server, db_user, db_password, matched_keyword=None):
    if role not in _ALLOWED_ROLES:
        return "Error: your role does not have access to this data."
    date_from, date_to, label = _period_dates(q)
    conn = _conn(db_name, db_server, db_user, db_password)
    if not conn:
        return "Error: could not connect to the database."
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM trninvstatus WHERE STATUS = 'Authenticated' "
            "AND AUTHENTICATEDATE >= ? AND AUTHENTICATEDATE < ?",
            (date_from, date_to),
        )
        n = cursor.fetchone()[0]
        return _dashboard_card(icon="👨‍⚕️", title="Authenticated (Doctor-Reviewed)", subtitle=label,
                                stats=[{"label": "COUNT", "value": f"{n:,}"}])
    except Exception as e:
        return f"Error: {e}"
    finally:
        conn.close()


# ---------- uhid_bills ----------
def _handle_uhid_bills(q, role, db_name, db_server, db_user, db_password, matched_keyword=None):
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
            "SELECT TOP 10 BILLNO, DATEOFBILL, PAIDAMOUNT FROM trnmodeofcollectionsdet "
            "WHERE UHID = ? ORDER BY DATEOFBILL DESC",
            (uhid,),
        )
        rows = cursor.fetchall()
        if not rows:
            return f"No bills found for UHID {uhid}."
        return _list_card(
            icon="🧾", title=f"Bills for {uhid}",
            items=[{"primary": bill, "fields": [f"{dt}", f"₹{float(amt or 0):,.0f}"]} for bill, dt, amt in rows],
        )
    except Exception as e:
        return f"Error: {e}"
    finally:
        conn.close()


# ---------- mode_only ----------
def _handle_mode_only(q, role, db_name, db_server, db_user, db_password, matched_keyword=None):
    if role not in _ALLOWED_ROLES:
        return "Error: your role does not have access to this data."
    mode_map = {"upi": "UPI", "cash": "CASH", "credit card": "CREDITCARD", "cheque": "CHEQUE"}
    mode = next((v for k, v in mode_map.items() if f"total {k}" in q), None)
    if not mode:
        return None
    date_from, date_to, label = _period_dates(q)
    conn = _conn(db_name, db_server, db_user, db_password)
    if not conn:
        return "Error: could not connect to the database."
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT SUM(PAIDAMOUNT) FROM trnmodeofcollectionsdet "
            "WHERE UPPER(LTRIM(RTRIM(MODE))) = ? AND DATEOFBILL >= ? AND DATEOFBILL < ?",
            (mode, date_from, date_to),
        )
        total = cursor.fetchone()[0] or 0
        return _dashboard_card(icon="💰", title=f"Total {mode.title()}", subtitle=label,
                                stats=[{"label": "AMOUNT", "value": f"₹{float(total):,.0f}"}])
    except Exception as e:
        return f"Error: {e}"
    finally:
        conn.close()
# ---------- locations_list ----------
def _handle_locations_list(q, role, db_name, db_server, db_user, db_password, matched_keyword=None):
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

def _handle_package_detail(q, role, db_name, db_server, db_user, db_password, matched_keyword=None):
    if role not in _ALLOWED_ROLES:
        return "Error: your role does not have access to this data."
    _known_locations = ["jagtial", "kompally", "kukatpally", "kokapet", "suryapet",
                         "uppal", "attapur", "alwal", "srikara-boduppal", "srikara-ecil",
                         "srikara-kompally", "srikara", "boduppal", "medchal", "medak", 
                         "warangal", "ecil", "kphb", "bengaluru fetal medicine", "bengaluru"]
    loc_m = re.search(
        r"\b(?:at|in|for)\s+(" + "|".join(_known_locations) + r")\b",
        q, re.IGNORECASE,
    )
    q_no_loc = (q[:loc_m.start()] + q[loc_m.end():]) if loc_m else q

    m = re.search(r"(?:package price for|what's in package|whats in package|package contents for|price for package)\s+(.+)", q_no_loc)
    term = m.group(1).strip() if m else None
    if not term or len(term) < 2:
        return None
    conn = _conn(db_name, db_server, db_user, db_password)
    if not conn:
        return "Error: could not connect to the database."
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT INVCODE, INVNAME FROM mstInvestigations "
            "WHERE ISPACKAGE = 'Y' AND INVNAME LIKE ? ORDER BY LEN(INVNAME) ASC",
            (f"%{term}%",),
        )
        candidates = cursor.fetchall()
        if not candidates:
            return None
        exact = [c for c in candidates if c[1].strip().lower() == term.strip().lower()]
        pkg = exact[0] if exact else candidates[0]
        if not pkg:
            return None
        pkg_code, pkg_name = pkg

        # Detect an optional location mention ("... at Jagtial", "... for Kompally")
        loc_filter_sql = ""
        loc_params = [pkg_code]
        loc_name = None
        if loc_m:
            loc_name = loc_m.group(1).strip()
            cursor.execute(
                "SELECT LOCATIONID FROM mstlocation WHERE LOCATIONNAME LIKE ?",
                (f"%{loc_name}%",),
            )
            loc_row = cursor.fetchone()
            if loc_row:
                loc_filter_sql = "AND p.LOCATIONID = ?"
                loc_params.append(loc_row[0])

        cursor.execute(
            f"SELECT DISTINCT p.PACKAGERATE, t.INVNAME, p.ACTUALRATE "
            f"FROM mstinvpackages p JOIN mstInvestigations t ON p.TESTCODE = t.INVCODE "
            f"WHERE p.PACKAGECODE = ? AND p.ACTIVE = 1 {loc_filter_sql}",
            tuple(loc_params),
        )
        rows = cursor.fetchall()
        if not rows:
            return f"No component tests found for package '{pkg_name}'."
        pkg_rate = rows[0][0]
        title_suffix = f" · {loc_name}" if loc_m and loc_row else ""
        return _list_card(
            icon="📦", title=pkg_name + title_suffix,
            intro=f"Package price: ₹{pkg_rate:,.0f}" if pkg_rate else None,
            items=[
                {"primary": test_name, "fields": [f"Individual rate: ₹{actual_rate:,.0f}"] if actual_rate else []}
                for _, test_name, actual_rate in rows
            ],
        )
    except Exception as e:
        return f"Error: {e}"
    finally:
        conn.close()

def _handle_packages_list(q, role, db_name, db_server, db_user, db_password, matched_keyword=None):
    if role not in _ALLOWED_ROLES:
        return "Error: your role does not have access to this data."
    conn = _conn(db_name, db_server, db_user, db_password)
    if not conn:
        return "Error: could not connect to the database."
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT TOP 15 INVNAME, RATE, TATTIME, TATTYPE FROM mstInvestigations "
            "WHERE ISPACKAGE = 'Y' AND ACTIVE = 1 AND INVNAME IS NOT NULL "
            "AND LTRIM(RTRIM(INVNAME)) != '' ORDER BY INVNAME"
        )
        rows = cursor.fetchall()
        if not rows:
            return "No packages found."
        items = []
        for name, rate, tat_time, tat_type in rows:
            fields = []
            if rate:
                fields.append(f"Rate: ₹{rate:,.0f}")
            if tat_time and tat_type:
                fields.append(f"TAT: {tat_time} {tat_type}")
            items.append({"primary": name, "fields": fields})
        return _list_card(
            icon="📦", title="Health Packages",
            intro="Note: pricing isn't set on most packages in this table — may live in a separate package-rates table (mstinvpackages).",
            items=items,
        )
    except Exception as e:
        return f"Error: {e}"
    finally:
        conn.close()
# ---------- referring_doctors ----------
def _handle_referring_doctors(q, role, db_name, db_server, db_user, db_password, matched_keyword=None):
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
                "WHERE p.BILLDATE >= ? AND p.BILLDATE < ? AND d.DOCNAME NOT LIKE '%SELF%' "
                "AND d.DOCNAME NOT LIKE '%HOSPITAL%' GROUP BY d.DOCNAME ORDER BY Cnt DESC",
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
def _handle_bill_detail(q, role, db_name, db_server, db_user, db_password, matched_keyword=None):
    if role not in _ALLOWED_ROLES:
        return "Error: your role does not have access to this data."
    m = re.search(
    r"\b(?:bill\s*(?:no\.?|number)?\s*[:\-]?\s*)?([A-Z]{2,4}\d{5,})\b",
    q.upper(),
)
# only treat as bill if 'bill' in q or pattern looks like KSU2619400
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
def _handle_departments_list(q, role, db_name, db_server, db_user, db_password, matched_keyword=None):
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


# ---------- recent_patients ----------
def _handle_recent_patients(q, role, db_name, db_server, db_user, db_password, matched_keyword=None):
    if role not in _ALLOWED_ROLES:
        return "Error: your role does not have access to this data."
    conn = _conn(db_name, db_server, db_user, db_password)
    if not conn:
        return "Error: could not connect to the database."
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT TOP 10 NAME, UHID, PHONENO, REGDATE FROM mstpatientregistration ORDER BY REGDATE DESC"
        )
        rows = cursor.fetchall()
        if not rows:
            return "No patient records found."
        return _list_card(
            icon="🧑‍🤝‍🧑", title="Recent Patients", intro="10 most recently registered:",
            items=[
                {"primary": name, "fields": [f"UHID: {uhid}", f"Phone: {phone}", f"Registered: {reg}"]}
                for name, uhid, phone, reg in rows
            ],
        )
    except Exception as e:
        return f"Error: {e}"
    finally:
        conn.close()

# ---------- test_volume ----------
def _handle_test_volume(q, role, db_name, db_server, db_user, db_password, matched_keyword=None):
    if role not in _ALLOWED_ROLES:
        return "Error: your role does not have access to this data."
    date_from, date_to, label = _period_dates(q)
    term_map = {"cbp": "CBP", "cue": "Complete Urine Analysis", "rbs": "RBS", "hba1c": "HBA1C"}
    term = next((v for k, v in term_map.items() if k in q), None)
    if not term:
        return None
    conn = _conn(db_name, db_server, db_user, db_password)
    if not conn:
        return "Error: could not connect to the database."
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM trninvlabdet d JOIN mstInvestigations i ON d.TCODE = i.INVCODE "
            "WHERE i.INVNAME LIKE ? AND d.BILLDATE >= ? AND d.BILLDATE < ?",
            (f"%{term}%", date_from, date_to),
        )
        n = cursor.fetchone()[0]
        return _dashboard_card(icon="🧪", title=f"{term} Volume", subtitle=label,
                                stats=[{"label": "COUNT", "value": f"{n:,}"}])
    except Exception as e:
        return f"Error: {e}"
    finally:
        conn.close()


# ---------- status_mix ----------
def _handle_status_mix(q, role, db_name, db_server, db_user, db_password, matched_keyword=None):
    if role not in _ALLOWED_ROLES:
        return "Error: your role does not have access to this data."
    date_from, date_to, label = _period_dates(q)
    conn = _conn(db_name, db_server, db_user, db_password)
    if not conn:
        return "Error: could not connect to the database."
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT TESTSTATUS, COUNT(*) FROM trninvlabdet WHERE BILLDATE >= ? AND BILLDATE < ? "
            "GROUP BY TESTSTATUS ORDER BY COUNT(*) DESC",
            (date_from, date_to),
        )
        rows = cursor.fetchall()
        if not rows:
            return f"No test-status data found for {label}."
        return _dashboard_card(
            icon="📊", title="Lab Status Breakdown", subtitle=label,
            stats=[{"label": (s or "(blank)").upper(), "value": f"{c:,}"} for s, c in rows],
        )
    except Exception as e:
        return f"Error: {e}"
    finally:
        conn.close()


# ---------- refunds ----------
def _handle_refunds(q, role, db_name, db_server, db_user, db_password, matched_keyword=None):
    if role not in _ALLOWED_ROLES:
        return "Error: your role does not have access to this data."
    date_from, date_to, label = _period_dates(q)
    conn = _conn(db_name, db_server, db_user, db_password)
    if not conn:
        return "Error: could not connect to the database."
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT SUM(PAIDAMOUNT) FROM trnmodeofcollectionsdet "
            "WHERE TYPE = 'LabRefund' AND DATEOFBILL >= ? AND DATEOFBILL < ?",
            (date_from, date_to),
        )
        total = cursor.fetchone()[0] or 0
        return _dashboard_card(icon="↩️", title="Total Refunds", subtitle=label,
                                stats=[{"label": "AMOUNT", "value": f"₹{float(total):,.0f}"}])
    except Exception as e:
        return f"Error: {e}"
    finally:
        conn.close()


# ---------- due_payments ----------
def _handle_due_payments(q, role, db_name, db_server, db_user, db_password, matched_keyword=None):
    if role not in _ALLOWED_ROLES:
        return "Error: your role does not have access to this data."
    date_from, date_to, label = _period_dates(q)
    conn = _conn(db_name, db_server, db_user, db_password)
    if not conn:
        return "Error: could not connect to the database."
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT SUM(PAIDAMOUNT) FROM trnmodeofcollectionsdet "
            "WHERE TYPE = 'DUE PAYMENT' AND DATEOFBILL >= ? AND DATEOFBILL < ?",
            (date_from, date_to),
        )
        total = cursor.fetchone()[0] or 0
        return _dashboard_card(icon="📮", title="Due Payments Received", subtitle=label,
                                stats=[{"label": "AMOUNT", "value": f"₹{float(total):,.0f}"}])
    except Exception as e:
        return f"Error: {e}"
    finally:
        conn.close()


# ---------- collection_by_location ----------
def _handle_collection_by_location(q, role, db_name, db_server, db_user, db_password, matched_keyword=None):
    if role not in _ALLOWED_ROLES:
        return "Error: your role does not have access to this data."
    date_from, date_to, label = _period_dates(q)
    conn = _conn(db_name, db_server, db_user, db_password)
    if not conn:
        return "Error: could not connect to the database."
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT l.LOCATIONNAME, SUM(m.PAIDAMOUNT) AS Amt FROM trnmodeofcollectionsdet m "
            "JOIN mstlocation l ON m.LOCATIONID = l.LOCATIONID "
            "WHERE m.DATEOFBILL >= ? AND m.DATEOFBILL < ? "
            "GROUP BY l.LOCATIONNAME ORDER BY Amt DESC",
            (date_from, date_to),
        )
        rows = cursor.fetchall()
        if not rows:
            return f"No collection data found for {label}."
        return _list_card(
            icon="📍", title=f"Collection by Branch · {label}",
            items=[{"primary": name, "fields": [f"₹{float(amt or 0):,.0f}"]} for name, amt in rows],
        )
    except Exception as e:
        return f"Error: {e}"
    finally:
        conn.close()


# ---------- bill_finance ----------
def _handle_bill_finance(q, role, db_name, db_server, db_user, db_password, matched_keyword=None):
    if role not in _ALLOWED_ROLES:
        return "Error: your role does not have access to this data."
    m = re.search(r"\b([A-Z]{2,4}\d{3,})\b", q.upper())
    if not m:
        return None
    billno = m.group(1)
    conn = _conn(db_name, db_server, db_user, db_password)
    if not conn:
        return "Error: could not connect to the database."
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT TOTALCHARGES, PAIDAMOUNT, CONCESSIONAMT, CREDITAMOUNT, RefundAmt, STATUS "
            "FROM trnINVLABPRI WHERE BILLNO = ?",
            (billno,),
        )
        row = cursor.fetchone()
        if not row:
            return f"No bill found with number {billno}."
        total, paid, conc, credit, refund, status = row
        stats = [
            {"label": "TOTAL CHARGES", "value": f"₹{float(total or 0):,.0f}"},
            {"label": "PAID", "value": f"₹{float(paid or 0):,.0f}"},
            {"label": "CONCESSION", "value": f"₹{float(conc or 0):,.0f}"},
            {"label": "CREDIT", "value": f"₹{float(credit or 0):,.0f}"},
        ]
        if refund:
            stats.append({"label": "REFUND", "value": f"₹{float(refund):,.0f}"})
        return _dashboard_card(icon="🧾", title=f"Bill {billno} · Finance", subtitle=status or "", stats=stats)
    except Exception as e:
        return f"Error: {e}"
    finally:
        conn.close()


# ---------- phone_lookup ----------
def _handle_phone_lookup(q, role, db_name, db_server, db_user, db_password, matched_keyword=None):
    if role not in _ALLOWED_ROLES:
        return "Error: your role does not have access to this data."
    m = re.search(r"\b(\d{10})\b", q)
    if not m:
        return None
    phone = m.group(1)
    conn = _conn(db_name, db_server, db_user, db_password)
    if not conn:
        return "Error: could not connect to the database."
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT TOP 5 NAME, UHID, PHONENO, REGDATE FROM mstpatientregistration WHERE PHONENO = ?",
            (phone,),
        )
        rows = cursor.fetchall()
        if not rows:
            return f"No patient found with phone {phone}."
        return _list_card(
            icon="📞", title=f"Patients with phone {phone}",
            items=[{"primary": n, "fields": [f"UHID: {u}", f"Registered: {r}"]} for n, u, _, r in rows],
        )
    except Exception as e:
        return f"Error: {e}"
    finally:
        conn.close()


# ---------- top_tests ----------
def _handle_top_tests(q, role, db_name, db_server, db_user, db_password, matched_keyword=None):
    if role not in _ALLOWED_ROLES:
        return "Error: your role does not have access to this data."
    date_from, date_to, label = _period_dates(q)
    conn = _conn(db_name, db_server, db_user, db_password)
    if not conn:
        return "Error: could not connect to the database."
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT TOP 10 i.INVNAME, COUNT(*) AS Cnt FROM trninvlabdet d "
            "JOIN mstInvestigations i ON d.TCODE = i.INVCODE "
            "WHERE d.BILLDATE >= ? AND d.BILLDATE < ? GROUP BY i.INVNAME ORDER BY Cnt DESC",
            (date_from, date_to),
        )
        rows = cursor.fetchall()
        if not rows:
            return f"No test volume data found for {label}."
        return _list_card(
            icon="🧪", title=f"Top Tests · {label}",
            items=[{"primary": name, "fields": [f"{c:,} orders"]} for name, c in rows],
        )
    except Exception as e:
        return f"Error: {e}"
    finally:
        conn.close()


# ---------- cancelled_tests ----------
def _handle_cancelled_tests(q, role, db_name, db_server, db_user, db_password, matched_keyword=None):
    if role not in _ALLOWED_ROLES:
        return "Error: your role does not have access to this data."
    date_from, date_to, label = _period_dates(q)
    conn = _conn(db_name, db_server, db_user, db_password)
    if not conn:
        return "Error: could not connect to the database."
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM trninvlabdet WHERE TESTSTATUS = 'Cancelled' "
            "AND BILLDATE >= ? AND BILLDATE < ?",
            (date_from, date_to),
        )
        n = cursor.fetchone()[0]
        return _dashboard_card(icon="🚫", title="Cancelled Tests", subtitle=label,
                                stats=[{"label": "COUNT", "value": f"{n:,}"}])
    except Exception as e:
        return f"Error: {e}"
    finally:
        conn.close()


# ---------- credit_bills ----------
def _handle_credit_bills(q, role, db_name, db_server, db_user, db_password, matched_keyword=None):
    if role not in _ALLOWED_ROLES:
        return "Error: your role does not have access to this data."
    conn = _conn(db_name, db_server, db_user, db_password)
    if not conn:
        return "Error: could not connect to the database."
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT TOP 20 BILLNO, TOTALCHARGES, BILLDATE FROM trnINVLABPRI "
            "WHERE (PAIDAMOUNT IS NULL OR PAIDAMOUNT = 0) AND TOTALCHARGES > 0 "
            "ORDER BY BILLDATE DESC"
        )
        rows = cursor.fetchall()
        if not rows:
            return "No unpaid/credit bills found."
        return _list_card(
            icon="💳", title="Unpaid / Credit Bills",
            items=[{"primary": bill, "fields": [f"₹{float(chg or 0):,.0f}", f"{dt}"]} for bill, chg, dt in rows],
        )
    except Exception as e:
        return f"Error: {e}"
    finally:
        conn.close()


# ---------- compare_collection ----------
def _handle_compare_collection(q, role, db_name, db_server, db_user, db_password, matched_keyword=None):
    if role not in _ALLOWED_ROLES:
        return "Error: your role does not have access to this data."
    today = date.today()
    this_start = today.replace(day=1)
    last_start = (this_start - timedelta(days=1)).replace(day=1)
    conn = _conn(db_name, db_server, db_user, db_password)
    if not conn:
        return "Error: could not connect to the database."
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT SUM(PAIDAMOUNT) FROM trnmodeofcollectionsdet WHERE DATEOFBILL >= ? AND DATEOFBILL < ?",
            (this_start.isoformat(), (today + timedelta(days=1)).isoformat()),
        )
        this_total = float(cursor.fetchone()[0] or 0)
        cursor.execute(
            "SELECT SUM(PAIDAMOUNT) FROM trnmodeofcollectionsdet WHERE DATEOFBILL >= ? AND DATEOFBILL < ?",
            (last_start.isoformat(), this_start.isoformat()),
        )
        last_total = float(cursor.fetchone()[0] or 0)
        growth = ((this_total - last_total) / last_total * 100) if last_total else None
        stats = [
            {"label": "THIS MONTH", "value": f"₹{this_total:,.0f}"},
            {"label": "LAST MONTH", "value": f"₹{last_total:,.0f}"},
        ]
        card = {"icon": "📈", "title": "Collection Growth", "stats": stats}
        if growth is not None:
            arrow = "▲" if growth >= 0 else "▼"
            card["footer"] = {"label": "Growth", "value": f"{arrow}{abs(growth):.1f}%"}
        return _dashboard_card(**card)
    except Exception as e:
        return f"Error: {e}"
    finally:
        conn.close()


# ---------- modality_volume ----------
def _handle_modality_volume(q, role, db_name, db_server, db_user, db_password, matched_keyword=None):
    if role not in _ALLOWED_ROLES:
        return "Error: your role does not have access to this data."
    date_from, date_to, label = _period_dates(q)
    modality_map = {
        "mri": "MRI", "ct scan": "CT", "ultrasound": "Ultrasound",
        "x-ray": "X-Ray", "xray": "X-Ray", "mammography": "Mammography", "2d echo": "2D ECHO",
    }
    term = next((v for k, v in modality_map.items() if k in q), None)
    if not term:
        return None
    conn = _conn(db_name, db_server, db_user, db_password)
    if not conn:
        return "Error: could not connect to the database."
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM trninvlabdet d JOIN mstInvestigations i ON d.TCODE = i.INVCODE "
            "WHERE i.INVNAME LIKE ? AND d.BILLDATE >= ? AND d.BILLDATE < ?",
            (f"%{term}%", date_from, date_to),
        )
        n = cursor.fetchone()[0]
        return _dashboard_card(icon="🩻", title=f"{term} Volume", subtitle=label,
                                stats=[{"label": "COUNT", "value": f"{n:,}"}])
    except Exception as e:
        return f"Error: {e}"
    finally:
        conn.close()

def _handle_lab_volume(q, role, db_name, db_server, db_user, db_password, matched_keyword=None):
    if role not in _ALLOWED_ROLES:
        return "Error: your role does not have access to this data."
    date_from, date_to, label = _period_dates(q)
    conn = _conn(db_name, db_server, db_user, db_password)
    if not conn:
        return "Error: could not connect to the database."
    try:
        cursor = conn.cursor()
        if "reject" in q:
            cursor.execute(
                "SELECT COUNT(*) FROM trninvlabdet "
                "WHERE BILLDATE >= ? AND BILLDATE < ? AND TESTSTATUS = 'Sample Rejected'",
                (date_from, date_to),
            )
            n = cursor.fetchone()[0]
            return _dashboard_card(
                icon="🚨", title="Sample Rejected", subtitle=label,
                stats=[{"label": "COUNT", "value": f"{n:,}"}],
            )
        if "pending" in q:
            cursor.execute(
                "SELECT COUNT(*) FROM trninvlabdet "
                "WHERE BILLDATE >= ? AND BILLDATE < ? AND TESTSTATUS = 'Pending'",
                (date_from, date_to),
            )
            n = cursor.fetchone()[0]
            return _dashboard_card(
                icon="⏳", title="Pending Tests", subtitle=label,
                stats=[{"label": "COUNT", "value": f"{n:,}"}],
            )
        cursor.execute(
            "SELECT COUNT(*) FROM trninvlabdet WHERE BILLDATE >= ? AND BILLDATE < ?",
            (date_from, date_to),
        )
        n = cursor.fetchone()[0]
        return _dashboard_card(
            icon="🧪", title="Lab Procedures", subtitle=label,
            stats=[{"label": "PROCEDURES", "value": f"{n:,}"}],
        )
    except Exception as e:
        return f"Error: {e}"
    finally:
        conn.close()


def _handle_day_collection_branch(q, role, db_name, db_server, db_user, db_password, matched_keyword=None):
    """Single-branch collection via curated tool."""
    if role not in _ALLOWED_ROLES:
        return "Error: your role does not have access to this data."
    from reports.curated_queries import get_day_collection, resolve_relative_date

    # strip noise words, leftover = location guess
    noise = [
        "collection", "day collection", "today", "yesterday", "this month", "last month",
        "this week", "last week", "cash", "upi", "card", "at", "for", "show", "me", "the",
        "total", "branch", "location", "centre", "center",
    ]
    loc = q
    for w in sorted(noise, key=len, reverse=True):
        loc = re.sub(rf"\b{re.escape(w)}\b", " ", loc)
    loc = re.sub(r"\d{4}-\d{2}-\d{2}", " ", loc)
    loc = loc.strip()
    if not loc or len(loc) < 3:
        return None  # fall through to LLM

    if "yesterday" in q:
        d0, d1 = "yesterday", "yesterday"
        label = "Yesterday"
    elif "this month" in q:
        d0, d1 = "this_month_start", date.today().isoformat()
        label = "This Month"
    else:
        d0, d1 = "today", "today"
        label = "Today"

    result = get_day_collection(loc, d0, d1, db_name, db_server, db_user, db_password)
    if result.get("error"):
        return f"Error: {result['error']}"
    if result.get("ambiguous"):
        return f"Multiple locations match '{loc}': {', '.join(result['candidates'])}."
    if result.get("no_data"):
        return f"No collection for {result.get('location', loc)} · {label}."
    total = result["total"]
    return _dashboard_card(
        icon="💰", title=f"Collection · {result['location']}", subtitle=label,
        stats=[{"label": "TOTAL", "value": f"₹{total:,.0f}"}],
        bar_section={
            "title": "By Mode",
            "rows": [
                {"label": str(b["mode"]), "value": float(b["amount"] or 0),
                 "extra": f"₹{float(b['amount'] or 0):,.0f}"}
                for b in result.get("breakdown", [])
            ],
        },
    )

def _handle_tat(q, role, db_name, db_server, db_user, db_password, matched_keyword=None):
    if role not in _ALLOWED_ROLES:
        return "Error: your role does not have access to this data."
    from agent.tools import check_tat_alert, get_tat_compliance_dashboard
    import re as _re
    m = _re.search(r"(\d+(?:\.\d+)?)\s*%", q)
    period = "yesterday" if "yesterday" in q else ("this_week" if "this week" in q else "today")

    _known_locations = ["jagtial", "kompally", "kukatpally", "kokapet", "suryapet",
                         "uppal", "attapur", "alwal", "srikara", "boduppal", "medchal",
                         "warangal", "ecil", "kphb", "bengaluru", "siricilla"]
    loc_m = _re.search(r"\b(" + "|".join(_known_locations) + r")\b", q, _re.IGNORECASE)
    location_keyword = loc_m.group(1) if loc_m else None

    if m or "compliance" in q or "alert" in q:
        raw = check_tat_alert.invoke({
            "threshold_pct": float(m.group(1)) if m else 80.0, "period": period,
            "location_keyword": location_keyword,
            "role": role, "db_name": db_name, "db_server": db_server,
            "db_user": db_user, "db_password": db_password,
        })
    else:
        raw = get_tat_compliance_dashboard.invoke({
            "period": period, "location_keyword": location_keyword,
            "role": role, "db_name": db_name,
            "db_server": db_server, "db_user": db_user, "db_password": db_password,
        })
    text = raw if isinstance(raw, str) else str(raw)
    if "```dashboard-card" in text or "```list-card" in text:
        return text
    if text.startswith("Error"):
        return text
    m = re.search(r"(\d+(?:\.\d+)?)%", text)
    icon = "🚨" if "🚨" in text or "below" in text else "⏱️"
    return _dashboard_card(
        icon=icon, title="TAT Compliance",
        stats=[{"label": "COMPLIANCE", "value": f"{m.group(1)}%" if m else text}],
        footer={"label": "Details", "value": text},
    )

# ---------- stuck_samples (Sample Collected still open) ----------
def _handle_stuck_samples(q, role, db_name, db_server, db_user, db_password, matched_keyword=None):
    if role not in _ALLOWED_ROLES:
        return "Error: your role does not have access to this data."
    today = date.today()
    date_from = (today - timedelta(days=7)).isoformat()
    date_to = (today + timedelta(days=1)).isoformat()
    conn = _conn(db_name, db_server, db_user, db_password)
    if not conn:
        return "Error: could not connect to the database."
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM trninvlabdet "
            "WHERE TESTSTATUS = 'Sample Collected' "
            "AND BILLDATE >= ? AND BILLDATE < ?",
            (date_from, date_to),
        )
        n = cursor.fetchone()[0]
        return _dashboard_card(
            icon="⏳", title="Stuck at Sample Collected",
            subtitle="Bills in last 7 days still Sample Collected",
            stats=[{"label": "COUNT", "value": f"{n:,}"}],
        )
    except Exception as e:
        return f"Error: {e}"
    finally:
        conn.close()


# ---------- top_tests_at_branch ----------
def _handle_top_tests_at_branch(q, role, db_name, db_server, db_user, db_password, matched_keyword=None):
    if role not in _ALLOWED_ROLES:
        return "Error: your role does not have access to this data."
    date_from, date_to, label = _period_dates(q)
    _known = [
        "jagtial", "kompally", "kukatpally", "suryapet", "uppal", "attapur",
        "alwal", "warangal", "kphb", "medchal", "siricilla", "bengaluru",
    ]
    loc_m = re.search(r"\b(" + "|".join(_known) + r")\b", q, re.IGNORECASE)
    if not loc_m:
        return None
    loc_kw = loc_m.group(1)
    conn = _conn(db_name, db_server, db_user, db_password)
    if not conn:
        return "Error: could not connect to the database."
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT LOCATIONID, LOCATIONNAME FROM mstlocation WHERE LOCATIONNAME LIKE ?",
            (f"%{loc_kw}%",),
        )
        locs = cursor.fetchall()
        if not locs:
            return f"No location matching '{loc_kw}'."
        if len(locs) > 1:
            exact = [r for r in locs if r[1].strip().lower() == loc_kw.lower()]
            locs = exact if len(exact) == 1 else locs
            if len(locs) > 1:
                return f"Multiple locations: {', '.join(r[1] for r in locs)}."
        loc_id, loc_name = locs[0]
        cursor.execute(
            "SELECT TOP 10 i.INVNAME, COUNT(*) AS Cnt FROM trninvlabdet d "
            "JOIN mstInvestigations i ON d.TCODE = i.INVCODE "
            "WHERE d.LOCATIONID = ? AND d.BILLDATE >= ? AND d.BILLDATE < ? "
            "GROUP BY i.INVNAME ORDER BY Cnt DESC",
            (loc_id, date_from, date_to),
        )
        rows = cursor.fetchall()
        if not rows:
            return f"No tests at {loc_name} for {label}."
        return _list_card(
            icon="🧪", title=f"Top Tests · {loc_name} · {label}",
            items=[{"primary": n, "fields": [f"{c:,}"]} for n, c in rows],
        )
    except Exception as e:
        return f"Error: {e}"
    finally:
        conn.close()


# ---------- refund_bills_list ----------
def _handle_refund_bills_list(q, role, db_name, db_server, db_user, db_password, matched_keyword=None):
    if role not in _ALLOWED_ROLES:
        return "Error: your role does not have access to this data."
    date_from, date_to, label = _period_dates(q)
    conn = _conn(db_name, db_server, db_user, db_password)
    if not conn:
        return "Error: could not connect to the database."
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT TOP 15 BILLNO, MODE, PAIDAMOUNT, DATEOFBILL "
            "FROM trnmodeofcollectionsdet "
            "WHERE TYPE = 'LabRefund' AND DATEOFBILL >= ? AND DATEOFBILL < ? "
            "ORDER BY DATEOFBILL DESC",
            (date_from, date_to),
        )
        rows = cursor.fetchall()
        if not rows:
            return f"No refund rows for {label}."
        return _list_card(
            icon="↩️", title=f"Recent Refunds · {label}",
            items=[
                {"primary": bill, "fields": [f"{mode}", f"₹{float(amt or 0):,.0f}", f"{dt}"]}
                for bill, mode, amt, dt in rows
            ],
        )
    except Exception as e:
        return f"Error: {e}"
    finally:
        conn.close()


# ---------- package_orders ----------
def _handle_package_orders(q, role, db_name, db_server, db_user, db_password, matched_keyword=None):
    if role not in _ALLOWED_ROLES:
        return "Error: your role does not have access to this data."
    date_from, date_to, label = _period_dates(q)
    conn = _conn(db_name, db_server, db_user, db_password)
    if not conn:
        return "Error: could not connect to the database."
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT TOP 10 i.INVNAME, COUNT(*) AS Cnt FROM trninvlabdet d "
            "JOIN mstInvestigations i ON d.TCODE = i.INVCODE "
            "WHERE i.ISPACKAGE = 'Y' AND d.BILLDATE >= ? AND d.BILLDATE < ? "
            "GROUP BY i.INVNAME ORDER BY Cnt DESC",
            (date_from, date_to),
        )
        rows = cursor.fetchall()
        if not rows:
            return f"No package orders for {label}."
        return _list_card(
            icon="📦", title=f"Top Packages Ordered · {label}",
            items=[{"primary": n, "fields": [f"{c:,} orders"]} for n, c in rows],
        )
    except Exception as e:
        return f"Error: {e}"
    finally:
        conn.close()


# ---------- branch_compare_collection ----------
def _handle_branch_compare(q, role, db_name, db_server, db_user, db_password, matched_keyword=None):
    """e.g. 'compare kompally vs uppal collection yesterday'"""
    if role not in _ALLOWED_ROLES:
        return "Error: your role does not have access to this data."
    m = re.search(r"compare\s+(.+?)\s+vs\s+(.+?)(?:\s+collection|\s+today|\s+yesterday|$)", q)
    if not m:
        m = re.search(r"(.+?)\s+vs\s+(.+?)(?:\s+collection)", q)
    if not m:
        return None
    a_kw, b_kw = m.group(1).strip(), m.group(2).strip()
    from reports.curated_queries import get_day_collection
    if "yesterday" in q:
        d0 = d1 = "yesterday"
        label = "Yesterday"
    elif "this month" in q:
        d0, d1 = "this_month_start", date.today().isoformat()
        label = "This Month"
    else:
        d0 = d1 = "today"
        label = "Today"
    ra = get_day_collection(a_kw, d0, d1, db_name, db_server, db_user, db_password)
    rb = get_day_collection(b_kw, d0, d1, db_name, db_server, db_user, db_password)
    if ra.get("error") or rb.get("error"):
        return f"Error: {ra.get('error') or rb.get('error')}"
    if ra.get("ambiguous") or rb.get("ambiguous"):
        return "One or both location names are ambiguous — be more specific."
    ta = 0.0 if ra.get("no_data") else float(ra.get("total") or 0)
    tb = 0.0 if rb.get("no_data") else float(rb.get("total") or 0)
    na = ra.get("location", a_kw)
    nb = rb.get("location", b_kw)
    return _dashboard_card(
        icon="📊", title=f"{na} vs {nb}", subtitle=label,
        stats=[
            {"label": na.upper()[:20], "value": f"₹{ta:,.0f}"},
            {"label": nb.upper()[:20], "value": f"₹{tb:,.0f}"},
            {"label": "DIFFERENCE", "value": f"₹{abs(ta - tb):,.0f}"},
        ],
    )

def _handle_cash_recon(q, role, db_name, db_server, db_user, db_password, matched_keyword=None):
    if role not in _ALLOWED_ROLES:
        return "Error: your role does not have access to this data."

    from agent.tools import get_lab_day_collection
    # ... rest unchanged

    noise = [
        "cash in hand", "reconciliation", "day collection reconciliation", "reconcil",
        "today", "yesterday", "this month", "for", "report", "detailed",
    ]
    loc = q
    for w in sorted(noise, key=len, reverse=True):
        loc = re.sub(rf"\b{re.escape(w)}\b", " ", loc)
    loc = loc.strip()
    if not loc or len(loc) < 3:
        return None

    date_from, _, label = _period_dates(q)
    raw = get_lab_day_collection.invoke({
        "location_keyword": loc,
        "bill_date": date_from,
        "role": role,
        "db_name": db_name,
        "db_server": db_server,
        "db_user": db_user,
        "db_password": db_password,
    })
    text = raw if isinstance(raw, str) else str(raw)
    if "```dashboard-card" in text or "```list-card" in text:
        return text  # tool already returned a card
    if text.startswith("Error"):
        return text

    stats = []
    for line in text.split("\n")[1:]:  # skip the "Real reconciliation..." header line
        line = line.strip()
        if not line or ":" not in line:
            continue
        label, _, value = line.partition(":")
        value = value.strip()
        m = re.search(r"Decimal\('([\d.\-]+)'\)", value)
        if m:
            amt = float(m.group(1))
            if amt == 0:
                continue  # skip zero/empty lines, keeps the card clean
            value = f"₹{amt:,.0f}"
        elif "None" in value:
            continue  # skip genuinely empty fields
        stats.append({"label": label.strip().upper(), "value": value})

    if not stats:
        return "No reconciliation data with real values found."

    header = text.split("\n")[0]
    subtitle = header.split(" for ")[-1] if " for " in header else ""
    subtitle = re.sub(r"\s*\(from.*?\):?\s*$", "", subtitle).strip()  # strip "(from dbo.LabDayCollection):"
    return _dashboard_card(icon="💰", title="Cash Reconciliation", subtitle=subtitle, stats=stats)

def _handle_dept_dashboard(q, role, db_name, db_server, db_user, db_password, matched_keyword=None):
    if role not in _ALLOWED_ROLES:
        return "Error: your role does not have access to this data."

    from agent.tools import get_department_dashboard

    dept = "laboratory"
    if "radiology" in q:
        dept = "radiology"
    elif "haematology" in q or "hematology" in q:
        dept = "haematology"
    elif "biochemistry" in q:
        dept = "biochemistry"
    elif "microbiology" in q:
        dept = "microbiology"

    known_periods = ["yesterday", "last week", "this week", "last month",
                      "this month", "this year", "today"]
    period_map = {
        "yesterday": "yesterday", "last week": "last_week", "this week": "this_week",
        "last month": "last_month", "this month": "this_month", "this year": "this_year",
        "today": "today",
    }
    matched_period = next((p for p in known_periods if p in q), None)
    if not matched_period:
        return None  # can't confidently parse this period — let the LLM's real date logic handle it
    period = period_map[matched_period]

    _known_locations = ["jagtial", "kompally", "kukatpally", "kokapet", "suryapet",
                         "uppal", "attapur", "alwal", "srikara-boduppal", "srikara-ecil",
                         "srikara-kompally", "srikara", "boduppal", "medchal",
                         "warangal", "ecil", "kphb", "bengaluru fetal medicine", "bengaluru"]
    loc_m = re.search(r"\b(" + "|".join(_known_locations) + r")\b", q, re.IGNORECASE)
    location_keyword = loc_m.group(1) if loc_m else None

    raw = get_department_dashboard.invoke({
        "department": dept,
        "period": period,
        "location": location_keyword,
        "role": role,
        "db_name": db_name,
        "db_server": db_server,
        "db_user": db_user,
        "db_password": db_password,
    })
    return raw if isinstance(raw, str) else str(raw)

_INTENTS = [
    # most specific first
    (["cash in hand", "reconciliation", "day collection reconciliation"],
     _handle_cash_recon),

    (["radiology dashboard", "lab dashboard", "laboratory dashboard",
      "haematology dashboard", "biochemistry dashboard", "microbiology dashboard",
      "radiology summary", "lab ops snapshot", "radiology numbers"],
     _handle_dept_dashboard),
    (["tat compliance", "tat alert", "overdue tat", "tests exceeding tat",
      "average tat", "radiology tat", "lab tat", "turnaround time"],
     _handle_tat),
    (["lab procedures", "how many lab procedures", "how many tests done",
      "sample rejected", "rejection count", "pending tests",
      "tests awaiting result", "lab workload"],
     _handle_lab_volume),
    (["list all packages", "list packages", "what packages", "which packages",
      "available packages", "health packages", "package list"],
     _handle_packages_list),
    (["package price for", "what's in package", "whats in package",
      "package contents for", "price for package"], 
     _handle_package_detail),
    (["total upi", "total cash collected", "total cash", "total credit card",
      "total cheque"], _handle_mode_only),
    (["organisation", "organization", "client company", "comp0"], _handle_org_lookup),
    (["ref doctor", "referring doctor named"], _handle_ref_doctor_lookup),
    (["how many bills", "bill count"], _handle_bills_count),
    (["total concession", "concessions this month"], _handle_concession_total),
    (["sample collected count", "samples collected"], _handle_sample_collected_count),
    (["authenticated count", "authenticated today"], _handle_authenticated_count),
    (["bills for uhid", "bills of patient"], _handle_uhid_bills),

    (["all branches collection", "total collection", "total paidamount",
      "collection by payment mode", "upi total", "today's collection data",
      "todays collection data", "overall collection", "grand total collection",
      "all branches collection", "payment mode wise collection",
      "cash vs upi", "total cash collected", "total upi"],
     _handle_all_collection),

    # single branch — AFTER all_collection so "total collection" doesn't hit this
    (["collection at", "collection for", "day collection", "branch collection",
      "kompally collection", "uppal collection", "kukatpally collection",
      "suryapet collection", "jagtial collection", "alwal collection",
      "attapur collection", "warangal collection"],
     _handle_day_collection_branch),

    (["patients registered", "how many patients", "how many new patients",
      "latest registrations", "registrations today", "new patients today"],
     _handle_patients_count),

    (["recent 10 patients", "recent patients", "latest patients",
      "last 10 patients", "show recent patients"],
     _handle_recent_patients),

    (["uhid", "patient with uhid", "find patient", "is uhid"],
     _handle_uhid_lookup),

    (["lookup cbp", "lookup test", "what is cue", "what is cbp",
      "complete urine analysis", "list urine tests", "list blood tests",
      "urine routine", "blood investigations", "find test rbs",
      "find test fbs", "find test hba1c", "investigation master",
      "is there a test called", "search investigation", "lipid profile",
      "rft", "lft", "hba1c"],
     _handle_test_lookup),

    (["cbp volume", "cbp count", "urine volume", "cue volume", "rbs volume",
      "hba1c volume"],
     _handle_test_volume),
    (["mri count", "ct scan", "ultrasound procedures", "x-ray count", "xray count",
      "mammography volume", "2d echo count"],
    _handle_modality_volume),
    (["status breakdown", "result entry count", "acknowledged count",
      "inv status mix"], 
    _handle_status_mix),
    (["refunds today", "total refunds", "lab refund"],
    _handle_refunds),
    (["due payment", "previous due", "outstanding due"], 
    _handle_due_payments),
    (["collection by branch", "collection by location", "top branches by collection"],
     _handle_collection_by_location),
    (["bill finance", "money for bill", "finance for bill"],
    _handle_bill_finance),
    (["find by phone", "phone lookup", "mobile "], 
    _handle_phone_lookup),
    (["top tests", "top investigations", "most ordered tests"], 
    _handle_top_tests),
    (["cancelled tests", "cancellation count"], 
    _handle_cancelled_tests),
    (["credit bills", "unpaid bills", "zero paid"], 
    _handle_credit_bills),
    (["this month vs last month collection", "collection growth", "best growth branch"],
     _handle_compare_collection),
    (["active locations", "active branches", "how many branches",
      "list all locations", "list all branches", "list locations",
      "branch list", "collection centres", "location codes"],
     _handle_locations_list),

    (["referring doctors", "top doctors", "top 10 referring",
      "top referring", "ref doctors", "who referred most"],
     _handle_referring_doctors),

    (["bill no", "bill number", "bill ", "details for bill", "show bill",
      "payment breakup bill", "status of bill"],
     _handle_bill_detail),

    (["list departments", "list all departments", "which departments",
      "department list"],
     _handle_departments_list),
]


def try_intent(question: str, role: str, db_name: str, db_server=None, db_user=None, db_password=None):
    """
    Returns an answer string (dashboard-card/list-card JSON, or a plain
    'no data'/'error' string) if a fixed-SQL intent matched and
    confidently answered, or None to fall through to the normal LLM path.
    """
    q = (question or "").strip().lower()
    for keywords, handler in _INTENTS:
        matched = next((kw for kw in keywords if kw in q), None)
        if matched:
            result = handler(q, role, db_name, db_server, db_user, db_password, matched_keyword=matched)
            if result is not None:
                return result
    return None