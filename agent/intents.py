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
from agent.schema_ctx import coll_amt, pri_amt, radiology_dept_sql, location_names, location_regex

_ALLOWED_ROLES = ("admin", "doctor", "reception")

class _UnrecognizedPeriod(Exception):
    pass

def _unsupported_extras(q: str, allowed_tokens: set) -> bool:
    """
    True if the question has filter words the handler will NOT apply.
    Then caller must return None so LLM handles it.
    """
    q = q.lower()
    extras = {
        "radiology", "laboratory", "haematology", "hematology", "biochemistry",
        "microbiology", "pathology", "cardiology",
        "for ", " at ", " in ", " of ",
        "by branch", "by location", "by doctor", "by department",
        "compare", " vs ", "growth", "trend",
        "package", "uhid", "bill no", "phone",
    }
    # strip allowed words so they don't count as extras
    cleaned = q
    for t in sorted(allowed_tokens, key=len, reverse=True):
        cleaned = cleaned.replace(t, " ")
    return any(x in cleaned for x in extras if x.strip())
def _period_dates(q: str):
    today = date.today()
    q = q.lower()

    if "yesterday" in q:
        d = today - timedelta(days=1)
        return d.isoformat(), (d + timedelta(days=1)).isoformat(), "Yesterday"
    if "last week" in q:
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

    # Whole named month, e.g. "August 2026", or ISO month "2026-08".
    # Deliberately placed after exact-day handling and before day-name parsing.
    month_names = {name: idx for idx, name in enumerate(
        ("january", "february", "march", "april", "may", "june",
         "july", "august", "september", "october", "november", "december"), 1)}
    named_month = re.search(
        r"\b(" + "|".join(month_names) + r")\s+(20\d{2})\b", q)
    iso_month = re.search(r"\b(20\d{2})-(0[1-9]|1[0-2])\b(?!-\d{2})", q)
    if named_month or iso_month:
        if named_month:
            month, year = month_names[named_month.group(1)], int(named_month.group(2))
        else:
            year, month = int(iso_month.group(1)), int(iso_month.group(2))
        start = date(year, month, 1)
        end = date(year + (month == 12), month % 12 + 1, 1)
        return start.isoformat(), end.isoformat(), start.strftime("%B %Y")

    # Specific named date, e.g. "april 20th 2025", "20 april 2025"
    months = {"january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
              "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12}
    m2 = re.search(r"\b(" + "|".join(months) + r")\s+(\d{1,2})\w*,?\s+(20\d{2})\b", q)
    if not m2:
        m2 = re.search(r"\b(\d{1,2})\w*\s+(" + "|".join(months) + r")\s+(20\d{2})\b", q)
        if m2:
            day_val, month_name, year_val = m2.group(1), m2.group(2), m2.group(3)
        else:
            month_name = day_val = year_val = None
    else:
        month_name, day_val, year_val = m2.group(1), m2.group(2), m2.group(3)

    if month_name:
        try:
            d_obj = date(int(year_val), months[month_name], int(day_val))
            d = d_obj.isoformat()
            return d, (d_obj + timedelta(days=1)).isoformat(), d
        except ValueError:
            pass  # invalid date like Feb 30 — fall through to unrecognized

    if "today" in q:
        return today.isoformat(), (today + timedelta(days=1)).isoformat(), "Today"

    raise _UnrecognizedPeriod(q)
def _require_period(q: str):
    """Returns (date_from, date_to, label) or raises _UnrecognizedPeriod."""
    return _period_dates(q)

def _dept_filter_in_question(q: str) -> bool:
    """True if user asked for a department this generic handler cannot filter."""
    return any(w in q for w in (
        "biochemistry", "haematology", "hematology", "microbiology",
        "pathology", "serology", "hormones", "radiology", "laboratory",
        "cardiology",
    ))  # genuinely unrecognized — caller must fall through to LLM, never silently default
def _conn(db_name, db_server, db_user, db_password):
    return get_hospital_connection(db_name, db_server, db_user, db_password)


def _prof(conn, db_name, db_server):
    from agent.schema_ctx import get_profile
    return get_profile(conn, db_name, db_server)


def _dashboard_card(**kwargs) -> str:
    return "```dashboard-card\n" + json.dumps(kwargs) + "\n```"


def _list_card(**kwargs) -> str:
    return "```list-card\n" + json.dumps(kwargs) + "\n```"


# ---------- all_collection ----------
def _handle_all_collection(q, role, db_name, db_server, db_user, db_password, matched_keyword=None):
    if role not in _ALLOWED_ROLES:
        return "Error: your role does not have access to this data."
    try:
        date_from, date_to, label = _period_dates(q)
    except _UnrecognizedPeriod:
        return None
    conn = _conn(db_name, db_server, db_user, db_password)
    if not conn:
        return "Error: could not connect to the database."
    try:
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT UPPER(LTRIM(RTRIM(MODE))) AS MODE, SUM({coll_amt(_prof(conn, db_name, db_server))}) AS Amt "
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
    try:
        date_from, date_to, label = _period_dates(q)
    except _UnrecognizedPeriod:
        return None
    conn = _conn(db_name, db_server, db_user, db_password)
    if not conn:
        return "Error: could not connect to the database."
    try:
        cursor = conn.cursor()
        _dc = _prof(conn, db_name, db_server)["pat_date"]
        cursor.execute(
            f"SELECT COUNT(*) FROM mstpatientregistration WHERE {_dc} >= ? AND {_dc} < ?",
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
    m = re.search(r"\buhid\s*[:\-]?\s*([A-Za-z0-9]*\d[A-Za-z0-9]{4,})\b", q, re.IGNORECASE)
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
    try:
        date_from, date_to, label = _period_dates(q)
    except _UnrecognizedPeriod:
        return None
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
        if not n:
            return None
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
    try:
        date_from, date_to, label = _period_dates(q)
    except _UnrecognizedPeriod:
        return None
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
    try:
        date_from, date_to, label = _period_dates(q)
    except _UnrecognizedPeriod:
        return None
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
        if not n:
            return None
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
    try:
        date_from, date_to, label = _period_dates(q)
    except _UnrecognizedPeriod:
        return None
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
        if not n:
            return None
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
            f"SELECT TOP 10 BILLNO, DATEOFBILL, {coll_amt(_prof(conn, db_name, db_server))} FROM trnmodeofcollectionsdet "
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
    mode_map = {
        "upi": ["UPI", "UPI PAYMENT", "PHONEPE", "GPAY", "GOOGLEPAY", "GOOGLE PAY", "PAYTM"],
        "cash": ["CASH"],
        "credit card": ["CREDITCARD", "CREDIT CARD", "CARD", "CC", "CREDIT_CARD", "DEBIT CARD", "DEBITCARD"],
        "cheque": ["CHEQUE", "CHECK", "CHQ", "DD"],
    }
    mode_key = next((k for k in mode_map if f"total {k}" in q or k in q), None)
    if not mode_key:
        return None
    aliases = mode_map[mode_key]
    try:
        date_from, date_to, label = _period_dates(q)
    except _UnrecognizedPeriod:
        return None
    conn = _conn(db_name, db_server, db_user, db_password)
    if not conn:
        return "Error: could not connect to the database."
    try:
        cursor = conn.cursor()
        placeholders = ",".join("?" * len(aliases))
        cursor.execute(
            f"SELECT SUM({coll_amt(_prof(conn, db_name, db_server))}) FROM trnmodeofcollectionsdet "
            f"WHERE UPPER(LTRIM(RTRIM(MODE))) IN ({placeholders}) "
            f"AND DATEOFBILL >= ? AND DATEOFBILL < ?",
            (*[a.upper() for a in aliases], date_from, date_to),
        )
        total = cursor.fetchone()[0] or 0
        return _dashboard_card(
            icon="💰", title=f"Total {mode_key.title()}", subtitle=label,
            stats=[{"label": "AMOUNT", "value": f"₹{float(total):,.0f}"}],
        )
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
    _names = location_names(db_name, db_server, db_user, db_password)
    loc_m = re.search(
        r"\b(?:at|in|for)\s+" + location_regex(_names),
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
    try:
        date_from, date_to, label = _period_dates(q)
    except _UnrecognizedPeriod:
        return None
    by_revenue = "revenue" in q
    conn = _conn(db_name, db_server, db_user, db_password)
    if not conn:
        return "Error: could not connect to the database."
    try:
        cursor = conn.cursor()
        if by_revenue:
            cursor.execute(
                f"SELECT TOP 10 d.DOCNAME, SUM({pri_amt(_prof(conn, db_name, db_server), 'p')}) AS Amt FROM trninvlabpri p "
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
    r"\b(?:bill\s*(?:no\.?|number)?\s*[:\-]?\s*)?([A-Z]{2,4}\d{3,})\b",
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
        # 1) header (any table that knows the bill)
        cursor.execute(
            "SELECT TOP 1 Name, Phone, TOTALCHARGES, STATUS FROM trnINVLABPRI WHERE BILLNO = ?",
            (billno,),
        )
        hdr = cursor.fetchone()
        # 2) tests, results optional (LEFT JOIN: bill may exist before results do)
        cursor.execute(
            "SELECT TOP 40 c.INVNAME, d.TESTSTATUS, p.PARAMHEADNAME, p.PVALUE, p.MINVALUE, p.MAXVALUE "
            "FROM trnINVLABDET d "
            "LEFT JOIN mstInvestigations c ON d.TCODE = c.INVCODE "
            "LEFT JOIN trnParamResult p ON p.BILLNO = d.BILLNO AND p.INVCODE = d.TCODE "
            "WHERE d.BILLNO = ?",
            (billno,),
        )
        rows = cursor.fetchall()
        # 3) collection-only bills
        coll = None
        if not hdr and not rows:
            cursor.execute(
                f"SELECT TOP 5 MODE, {coll_amt(_prof(conn, db_name, db_server))}, DATEOFBILL "
                "FROM trnmodeofcollectionsdet WHERE BILLNO = ?",
                (billno,),
            )
            coll = cursor.fetchall()
        if not hdr and not rows and not coll:
            return f"No records found for bill {billno}."
        if not hdr and not rows:
            return _list_card(
                icon="🧾", title=f"Bill {billno}", intro="Collection record only",
                items=[{"primary": str(m), "fields": [f"₹{float(a or 0):,.0f}", str(d)]} for m, a, d in coll],
            )
        intro = f"{hdr[0]} · {hdr[1]}" if hdr else ""
        items = []
        for inv, st, param, pval, minv, maxv in rows[:20]:
            if pval is None:
                items.append({"primary": inv or "Test", "fields": [f"Status: {st or 'Pending'}"]})
                continue
            fields = [f"Value: {pval}"]
            if minv is not None and maxv is not None:
                fields.append(f"Range: {minv}-{maxv}")
            items.append({"primary": f"{inv} — {param}" if param else (inv or "Test"), "fields": fields})
        if not items:
            items = [{"primary": "No tests on this bill", "fields": []}]
        return _list_card(icon="🧾", title=f"Bill {billno}", intro=intro, items=items)
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
        pr = _prof(conn, db_name, db_server)
        phone_expr = "COALESCE(" + ", ".join(f"NULLIF(LTRIM(RTRIM(CAST({c} AS VARCHAR(30)))), '')" for c in pr["pat_phones"]) + ", '')"
        cursor.execute(
            f"SELECT TOP 10 {pr['pat_name']}, UHID, {phone_expr}, {pr['pat_date']} "
            f"FROM mstpatientregistration ORDER BY {pr['pat_date']} DESC"
        )
        rows = cursor.fetchall()
        if not rows:
            return "No patient records found."

        def _d(v):
            try:
                return v.strftime("%d %b %Y, %I:%M %p")
            except Exception:
                return str(v)[:16]

        return _list_card(
            icon="🧑‍🤝‍🧑", title="Recent Patients", intro="10 most recently registered:",
            items=[
                {"primary": name, "fields": [f"UHID: {uhid}"] + ([f"Phone: {phone}"] if phone else []) + [f"Registered: {_d(reg)}"]}
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
    try:
        date_from, date_to, label = _period_dates(q)
    except _UnrecognizedPeriod:
        return None
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
        if not n:
            return None
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
    try:
        date_from, date_to, label = _period_dates(q)
    except _UnrecognizedPeriod:
        return None
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
    try:
        date_from, date_to, label = _period_dates(q)
    except _UnrecognizedPeriod:
        return None
    conn = _conn(db_name, db_server, db_user, db_password)
    if not conn:
        return "Error: could not connect to the database."
    try:
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT SUM({coll_amt(_prof(conn, db_name, db_server))}) FROM trnmodeofcollectionsdet "
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
    try:
        date_from, date_to, label = _period_dates(q)
    except _UnrecognizedPeriod:
        return None
    conn = _conn(db_name, db_server, db_user, db_password)
    if not conn:
        return "Error: could not connect to the database."
    try:
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT SUM({coll_amt(_prof(conn, db_name, db_server))}) FROM trnmodeofcollectionsdet "
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
    # compare / growth / two periods → LLM (or dedicated compare handler)
    ql = q.lower()
    if any(x in ql for x in (
        "compar", " vs ", "versus", "growth", "better than", "worse than",
        "compared to", "relative to",
    )):
        return None
    if ("this month" in ql and "last month" in ql) or ("this week" in ql and "last week" in ql):
        return None
    try:
        date_from, date_to, label = _period_dates(q)
    except _UnrecognizedPeriod:
        return None
    conn = _conn(db_name, db_server, db_user, db_password)
    if not conn:
        return "Error: could not connect to the database."
    try:
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT COALESCE(l.LOCATIONNAME, CAST(m.LOCATIONID AS VARCHAR(50)), 'Unknown') AS LOCATIONNAME, "
            f"SUM({coll_amt(_prof(conn, db_name, db_server), 'm')}) AS Amt "
            "FROM trnmodeofcollectionsdet m "
            "LEFT JOIN mstlocation l ON CAST(m.LOCATIONID AS VARCHAR(50)) = CAST(l.LOCATIONID AS VARCHAR(50)) "
            "WHERE m.DATEOFBILL >= ? AND m.DATEOFBILL < ? "
            "GROUP BY COALESCE(l.LOCATIONNAME, CAST(m.LOCATIONID AS VARCHAR(50)), 'Unknown') "
            "ORDER BY Amt DESC",
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
    try:
        date_from, date_to, label = _period_dates(q)
    except _UnrecognizedPeriod:
        return None
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
    try:
        date_from, date_to, label = _period_dates(q)
    except _UnrecognizedPeriod:
        return None
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
        if not n:
            return None
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
            "WHERE (ISNULL(CREDITAMOUNT,0) > 0 OR ISNULL(PAIDAMOUNT,0) = 0) AND TOTALCHARGES > 0 "
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
        _amt = coll_amt(_prof(conn, db_name, db_server))
        cursor.execute(
            f"SELECT SUM({_amt}) FROM trnmodeofcollectionsdet WHERE DATEOFBILL >= ? AND DATEOFBILL < ?",
            (this_start.isoformat(), (today + timedelta(days=1)).isoformat()),
        )
        this_total = float(cursor.fetchone()[0] or 0)
        cursor.execute(
            f"SELECT SUM({_amt}) FROM trnmodeofcollectionsdet WHERE DATEOFBILL >= ? AND DATEOFBILL < ?",
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

def _is_comparison_question(q: str) -> bool:
    ql = (q or "").lower()
    if any(x in ql for x in ("compar", " vs ", "versus", "growth", "compared to", "better than", "worse than")):
        return True
    if ("this month" in ql and "last month" in ql) or ("this week" in ql and "last week" in ql):
        return True
    if ("this year" in ql and "last year" in ql):
        return True
    return False
# ---------- modality_volume ----------
def _handle_modality_volume(q, role, db_name, db_server, db_user, db_password, matched_keyword=None):
    if role not in _ALLOWED_ROLES:
        return "Error: your role does not have access to this data."
    try:
        date_from, date_to, label = _period_dates(q)
    except _UnrecognizedPeriod:
        return None
    modality_map = {
        "mri": "MRI", "ct scan": "CT", "ultrasound": "Ultrasound",
        "x-ray": "X-Ray", "xray": "X-Ray", "mammography": "Mammography", "2d echo": "Echo",
    }
    term = next((v for k, v in modality_map.items() if k in q), None)
    if not term:
        return None
    conn = _conn(db_name, db_server, db_user, db_password)
    if not conn:
        return "Error: could not connect to the database."
    try:
        cursor = conn.cursor()
        from agent.report_tool import _MODALITY_CASE   # word-bounded names: "CT" must not match "Direct Bilirubin"
        cursor.execute(
            "SELECT COUNT(*) FROM trninvlabdet d JOIN mstInvestigations i ON d.TCODE = i.INVCODE "
            f"WHERE ({_MODALITY_CASE}) = ? AND d.BILLDATE >= ? AND d.BILLDATE < ?",
            (term, date_from, date_to),
        )
        n = cursor.fetchone()[0]
        if not n:
            return None
        return _dashboard_card(icon="🩻", title=f"{term} Volume", subtitle=label,
                                stats=[{"label": "COUNT", "value": f"{n:,}"}])
    except Exception as e:
        return f"Error: {e}"
    finally:
        conn.close()

def _handle_lab_volume(q, role, db_name, db_server, db_user, db_password, matched_keyword=None):
    if role not in _ALLOWED_ROLES:
        return "Error: your role does not have access to this data."
    try:
        date_from, date_to, label = _period_dates(q)
    except _UnrecognizedPeriod:
        return None
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
            return _dashboard_card(icon="🚨", title="Sample Rejected", subtitle=label,
                                   stats=[{"label": "COUNT", "value": f"{n:,}"}])
        if "pending" in q or "awaiting result" in q:
            cursor.execute(
                "SELECT COUNT(*) FROM trninvlabdet "
                "WHERE BILLDATE >= ? AND BILLDATE < ? AND TESTSTATUS = 'Pending'",
                (date_from, date_to),
            )
            n = cursor.fetchone()[0]
            return _dashboard_card(icon="⏳", title="Pending Tests", subtitle=label,
                                   stats=[{"label": "COUNT", "value": f"{n:,}"}])
        cursor.execute(
            "SELECT COUNT(*) FROM trninvlabdet WHERE BILLDATE >= ? AND BILLDATE < ?",
            (date_from, date_to),
        )
        n = cursor.fetchone()[0]
        return _dashboard_card(icon="🧪", title="Lab Procedures", subtitle=label,
                               stats=[{"label": "PROCEDURES", "value": f"{n:,}"}])
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
    elif "today" in q:
        d0, d1 = "today", "today"
        label = "Today"
    else:
        # last week / last month / this week / no period → LLM
        return None

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

    # Avoid guessing unsupported department-specific TAT joins.
    if _dept_filter_in_question(q):
        return None

    # TAT dashboard accepts historic month:YYYY-MM and day/specific_date.
    # Parse concrete dates before relative periods; never silently use Today.
    from datetime import date as _date
    import calendar
    specific_date = None
    m_day = re.search(r"\b(20\d{2}-\d{2}-\d{2})\b", q)
    month_names = {name.lower(): idx for idx, name in enumerate(calendar.month_name) if name}
    m_named_day = re.search(r"\b(" + "|".join(month_names) + r")\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(20\d{2})\b", q)
    m_named_day_reverse = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(" + "|".join(month_names) + r")\s+(20\d{2})\b", q)
    m_month = re.search(r"\b(" + "|".join(month_names) + r")\s+(20\d{2})\b", q)
    m_iso_month = re.search(r"\b(20\d{2})-(0[1-9]|1[0-2])\b(?!-\d{2})", q)
    m_year = re.search(r"\b(20\d{2})\b", q)
    try:
        if m_day:
            specific_date = _date.fromisoformat(m_day.group(1)).isoformat()
            period = "day"
        elif m_named_day:
            specific_date = _date(int(m_named_day.group(3)), month_names[m_named_day.group(1)], int(m_named_day.group(2))).isoformat()
            period = "day"
        elif m_named_day_reverse:
            specific_date = _date(int(m_named_day_reverse.group(3)), month_names[m_named_day_reverse.group(2)], int(m_named_day_reverse.group(1))).isoformat()
            period = "day"
        elif m_month:
            period = f"month:{m_month.group(2)}-{month_names[m_month.group(1)]:02d}"
        elif m_iso_month:
            period = f"month:{m_iso_month.group(1)}-{m_iso_month.group(2)}"
        elif "last month" in q:
            period = "last_month"
        elif "this month" in q:
            period = "this_month"
        elif "last week" in q:
            period = "last_week"
        elif "this week" in q:
            period = "this_week"
        elif "yesterday" in q:
            period = "yesterday"
        elif "today" in q:
            period = "today"
        elif "last 7" in q:
            period = "last_7_days"
        elif "last 30" in q:
            period = "last_30_days"
        elif "this year" in q:
            period = "this_year"
        elif "last year" in q:
            period = f"year:{_date.today().year - 1}"
        elif m_year:
            period = f"year:{m_year.group(1)}"
        else:
            period = "today"
    except ValueError:
        return "Error: invalid TAT reporting date."

    from agent.tools import get_tat_compliance_dashboard
    m_threshold = re.search(r"(\d+(?:\.\d+)?)\s*%", q)
    loc_m = re.search(r"\b" + location_regex(location_names(db_name, db_server, db_user, db_password)), q, re.IGNORECASE)
    location_keyword = loc_m.group(1) if loc_m else None

    # Use the SAME completed-test window for TAT compliance and overdue
    # summaries, rather than an alert tool with different date support.
    raw = get_tat_compliance_dashboard.invoke({
        "period": period,
        "specific_date": specific_date,
        "location_keyword": location_keyword,
        "role": role,
        "db_name": db_name,
        "db_server": db_server,
        "db_user": db_user,
        "db_password": db_password,
    })
    text = raw if isinstance(raw, str) else str(raw)
    if "```dashboard-card" in text or "```list-card" in text:
        return text
    if text.startswith("Error"):
        return text
    # Make zero-data state readable, rather than showing a long sentence as
    # the numeric COMPLIANCE metric. No duplicate text in the footer.
    if "No completed tests" in text or "No data found" in text:
        return _dashboard_card(icon="⏱️", title="TAT Compliance", subtitle=period,
                               stats=[{"label": "COMPLETED", "value": "0"}],
                               footer={"label": "Details", "value": text})
    m_pct = re.search(r"(\d+(?:\.\d+)?)%", text)
    return _dashboard_card(
        icon="⏱️", title="TAT Compliance", subtitle=period,
        stats=[{"label": "COMPLIANCE", "value": f"{m_pct.group(1)}%" if m_pct else "N/A"}],
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
        if not n:
            return None
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
    try:
        date_from, date_to, label = _period_dates(q)
    except _UnrecognizedPeriod:
        return None
    loc_m = re.search(r"\b" + location_regex(location_names(db_name, db_server, db_user, db_password)), q, re.IGNORECASE)
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

def _handle_cash_recon(q, role, db_name, db_server, db_user, db_password, matched_keyword=None):
    if role not in _ALLOWED_ROLES:
        return "Error: your role does not have access to this data."
    from reports.day_collection_reconciliation import (
        get_day_collection_one_branch, get_day_collection_all_branches,
        format_reconciliation_card_fields,
    )

    try:
        date_from, _, label = _period_dates(q)
    except _UnrecognizedPeriod:
        return None
    is_all_branches = any(kw in q for kw in ["all branches", "all locations", "every branch", "overall"])

    if is_all_branches:
        result = get_day_collection_all_branches(date_from, db_name, db_server, db_user, db_password)
        if "error" in result:
            return f"Error: {result['error']}"
        items = []
        for b in sorted(result["branches"], key=lambda x: -(x.get("TOTALCASHINHAND") or 0)):
            fields = format_reconciliation_card_fields(b)
            cash_in_hand = next((v for k, v in fields if "Cash in Hand" in k), 0)
            items.append({"primary": b["LOCATION"], "fields": [f"Cash in Hand: ₹{cash_in_hand:,.0f}"]})
        return _list_card(icon="💰", title=f"Cash Reconciliation · All Branches · {result['bill_date']}", items=items)

    noise = ["cash in hand", "reconciliation", "day collection reconciliation", "reconcil",
             "today", "yesterday", "this month", "for", "report", "detailed"]
    loc = q
    for w in sorted(noise, key=len, reverse=True):
        loc = re.sub(rf"\b{re.escape(w)}\b", " ", loc)
    loc = loc.strip()
    if not loc or len(loc) < 3:
        return None

    result = get_day_collection_one_branch(loc, date_from, db_name, db_server, db_user, db_password)
    if "error" in result:
        return f"Error: {result['error']}"

    branch = result["branch"]
    fields = format_reconciliation_card_fields(branch)
    return _dashboard_card(
        icon="💰", title=f"Cash Reconciliation · {branch['LOCATION']}", subtitle=result["bill_date"],
        stats=[{"label": label_text, "value": f"₹{val:,.0f}"} for label_text, val in fields],
    )
# ---------- refund_bills_list ----------
def _handle_refund_bills_list(q, role, db_name, db_server, db_user, db_password, matched_keyword=None):
    if role not in _ALLOWED_ROLES:
        return "Error: your role does not have access to this data."
    try:
        date_from, date_to, label = _period_dates(q)
    except _UnrecognizedPeriod:
        return None
    conn = _conn(db_name, db_server, db_user, db_password)
    if not conn:
        return "Error: could not connect to the database."
    try:
        cursor = conn.cursor()
        cursor.execute(
            f"SELECT TOP 15 BILLNO, MODE, {coll_amt(_prof(conn, db_name, db_server))}, DATEOFBILL "
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

#def _handle_excel_export(q, role, db_name, db_server, db_user, db_password, matched_keyword=None):
 #   if role not in _ALLOWED_ROLES:
  #      return "Error: your role does not have access to this data."
   # period = "yesterday" if "yesterday" in q else ("this_month" if "this month" in q else "today")
    #from reports.excel_export import export_all_branches_collection
#    result = export_all_branches_collection(period, db_name, db_server, db_user, db_password)
 #   if "error" in result:
  #      return f"Error: {result['error']}"
   # return f"📊 Excel export ready: {result['filename']} (download link needed — see backend wiring)"

# ---------- package_orders ----------
def _handle_package_orders(q, role, db_name, db_server, db_user, db_password, matched_keyword=None):
    if role not in _ALLOWED_ROLES:
        return "Error: your role does not have access to this data."
    try:
        date_from, date_to, label = _period_dates(q)
    except _UnrecognizedPeriod:
        return None
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
    elif "today" in q:
        d0 = d1 = "today"
        label = "Today"
    else:
        return None  # unrecognized period (e.g. "whole 2026") — let the LLM's real date logic handle it
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

    loc_m = re.search(r"\b" + location_regex(location_names(db_name, db_server, db_user, db_password)), q, re.IGNORECASE)
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
    (["this month vs last month collection", "collection growth", "best growth branch"],
     _handle_compare_collection),
    (["compare ", " vs "], _handle_branch_compare),
    # most specific first
    (["cash in hand", "reconciliation", "day collection reconciliation"],
     _handle_cash_recon),

    (["radiology dashboard", "lab dashboard", "laboratory dashboard",
      "haematology dashboard", "biochemistry dashboard", "microbiology dashboard",
      "radiology summary", "lab ops snapshot", "radiology numbers"],
     _handle_dept_dashboard),
    (["tat compliance", "tat alert", "overdue tat", "tests exceeding tat",
      "tat for", "tat report", "tat summary", "tat dashboard",
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

    (["all branches collection", "total collection", "today\'s collection", "todays collection",
      "yesterday\'s collection", "yesterdays collection", "total paidamount",
      "collection by payment mode", "upi total", "today's collection data",
      "todays collection data", "overall collection", "grand total collection",
      "all branches collection", "payment mode wise collection",
      "cash vs upi", "total cash collected", "total upi"],
     _handle_all_collection),
    (["stuck samples", "sample collected pending", "still sample collected"],
     _handle_stuck_samples),
    (["top tests at", "top investigations at", "tests at"],
     _handle_top_tests_at_branch),
    (["list refunds", "recent refunds", "refund bills"], _handle_refund_bills_list),
    (["top packages", "package orders", "packages ordered"], _handle_package_orders),
#    (["export collection to excel", "excel export", "download collection excel"],
#    _handle_excel_export),
    # single branch — AFTER all_collection so "total collection" doesn't hit this
    (["collection at", "collection for", "day collection", "branch collection",
      "branch day collection"],
     _handle_day_collection_branch),

    (["patients registered", "how many patients", "how many new patients",
      "latest registrations", "registrations today", "new patients today"],
     _handle_patients_count),

    (["recent 10 patients", "recent patients", "latest patients",
      "last 10 patients", "show recent patients", "recent top 10 patients",
      "top 10 patients", "top 10 recent patients", "newest patients",
      "all patients", "show all patients", "show me all patients", "list patients"],
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
    (["collection by branch", "collection by location", "top branches by collection",
      "best branch", "top performing", "performing the best", "performing best",
      "which branch", "top branch", "branch performance", "best performing"],
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

import sys
from agent.intents_lis_extra import build_extra_intents
_INTENTS = build_extra_intents(sys.modules[__name__]) + _INTENTS


_COLLECTION_WORDS = ("collection", "revenue", "sales", "income", "business")
_OTHER_TOPICS = ("doctor", "refund", "radiology", "lab revenue", "test", "patient", "bill", "concession",
                 "discount", "cancel", "sample", "tat", "package", "referr", "department", "ct ", "mri",
                 "ultrasound", "x-ray", "xray")
# Words that mean "analysis the fixed intents cannot do" -> go straight to the LLM.
_ANALYTIC = re.compile(
    r"\b(average|avg|per day|per branch|per doctor|each day|each branch|daily|trend|only one|only 1|"
    r"more than|less than|greater than|fewer than|than last|lowest|highest|least|most|share of|percentage|"
    r"breach(?:ed)?|older than|which day|which branch (?:does|has|have|is|had)|which doctor|which test|"
    r"which tests|not at|but not|without|repeat|visited|per modality|by modality|modality|versus)\b"
)
# questions that deliberately use one of those words but ARE served by an instant intent
_ANALYTIC_OK = ("top ", "most ordered", "highest collection", "best", "top-performing")


def _needs_llm(q: str) -> bool:
    if not _ANALYTIC.search(q):
        return False
    return not any(k in q for k in _ANALYTIC_OK)


# Custom Query List: conservative deterministic dispatch.  Exact phrases only.
# This avoids capturing client-specific names/filters that need schema-aware logic.
# Unsupported reports still follow the established LLM/report-tool route.
_CUSTOM_EXACT = {
    # Business / finance: re-use schema_ctx coll_amt (including per-client pins).
    "today's collection": ("_handle_all_collection", "today's collection"),
    "how much did we collect?": ("_handle_all_collection", "today's collection"),
    "how much did we collect yesterday?": ("_handle_all_collection", "yesterday's collection"),
    "payment mode split": ("_handle_all_collection", "today's collection"),
    "cash vs upi": ("_handle_all_collection", "today's collection"),
    "month to date": ("_handle_all_collection", "this month collection"),
    "year to date": ("_handle_all_collection", "this year collection"),
    "today's discount": ("_handle_concession_total", "total concession today"),
    "refunds today": ("_handle_refunds", "refunds today"),
    # Patients and doctors
    "how many patients today?": ("_handle_patients_count", "how many patients today"),
    "patient count today": ("_handle_patients_count", "how many patients today"),
    "top referral doctors": ("_handle_referring_doctors", "top referring doctors today"),
    "top doctors today": ("_handle_referring_doctors", "top doctors today"),
    # Laboratory
    "lab status": ("_handle_status_mix", "status breakdown today"),
    "sample rejection": ("_handle_lab_volume", "sample rejected today"),
    "rejected samples": ("_handle_lab_volume", "sample rejected today"),
    "how many ct scans today?": ("_handle_modality_volume", "ct scan today"),
    "how many mri scans?": ("_handle_modality_volume", "mri count today"),
    "x-ray today": ("_handle_modality_volume", "x-ray count today"),
    "mammography today": ("_handle_modality_volume", "mammography volume today"),
    "top 10 tests": ("_handle_top_tests", "top tests today"),
    "most ordered tests": ("_handle_top_tests", "top tests today"),
    "top tests today": ("_handle_top_tests", "top tests today"),
    # Branch / packages
    "top packages": ("_handle_package_orders", "top packages today"),
}

# Do not force explanatory, hypothetical, or speculative questions into today's
# numeric dashboard. Return None so the normal non-intent flow can answer them.
_NON_REPORT_PREFIXES = (
    "explain ", "why ", "what does ", "what is the difference ",
    "how does ", "can you explain ", "show tat compliance for a date",
    "show tat for a date", "is ", "should ",
)

# Direct TAT route precedes _ANALYTIC which otherwise rejects 'average'.
_TAT_REPORT_TERMS = (
    "tat report", "tat dashboard", "tat compliance", "today's tat",
    "todays tat", "average tat", "avg tat", "turnaround time report",
    "turnaround time dashboard",
)

def _custom_route(q, role, db_name, db_server, db_user, db_password):
    if q.startswith(_NON_REPORT_PREFIXES):
        return None
    match = _CUSTOM_EXACT.get(q)
    if match:
        handler_name, canonical = match
        handler = globals()[handler_name]
        return handler(canonical, role, db_name, db_server, db_user, db_password,
                       matched_keyword=canonical)
    if any(term in q for term in _TAT_REPORT_TERMS) and not _is_comparison_question(q):
        # Avoid replacing the user's date or location with 'today'.
        return _handle_tat(q, role, db_name, db_server, db_user, db_password)
    return None


def try_intent(question: str, role: str, db_name: str, db_server=None, db_user=None, db_password=None):
    q = (question or "").strip().lower()

    # Custom exact aliases, plus early TAT dispatch (before analytics gate).
    # No client DB writes; handlers retain their own roles, schema profiles and SQL.
    if q.startswith(_NON_REPORT_PREFIXES):
        return None
    custom = _custom_route(q, role, db_name, db_server, db_user, db_password)
    if custom is not None:
        return custom

    # 1) Collection growth / branch-vs-branch ONLY when the question is purely about collection.
    #    "doctors this month vs last month", "refunds by branch compared with last month",
    #    "radiology vs lab revenue" etc. are NOT collection growth -> LLM.
    if _is_comparison_question(q):
        pure_collection = any(w in q for w in _COLLECTION_WORDS) and not any(w in q for w in _OTHER_TOPICS)
        r = _handle_branch_compare(q, role, db_name, db_server, db_user, db_password)
        if r is not None:
            return r
        if pure_collection:
            r = _handle_compare_collection(q, role, db_name, db_server, db_user, db_password)
            if r is not None:
                return r
        return None  # LLM

    # 2) Analytic wording the fixed intents cannot answer -> LLM
    if _needs_llm(q):
        return None

    for keywords, handler in _INTENTS:
        matched = next((kw for kw in keywords if kw in q), None)
        if matched:
            try:
                result = handler(q, role, db_name, db_server, db_user, db_password, matched_keyword=matched)
            except _UnrecognizedPeriod:
                return None
            return result  # None → LLM; do not try another intent
    fixed = _fix_typos(q)
    if fixed != q:
        return try_intent(fixed, role, db_name, db_server, db_user, db_password)
    return None

from agent.normalize import build_vocab, correct_typos

_VOCAB = None


def _fix_typos(q: str) -> str:
    """Spelling-tolerant routing — only tried when NO intent matched the question as typed."""
    global _VOCAB
    if _VOCAB is None:
        _VOCAB = build_vocab(kw for kws, _ in _INTENTS for kw in kws)
    return correct_typos(q, _VOCAB)