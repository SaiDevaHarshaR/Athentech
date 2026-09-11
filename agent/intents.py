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
    loc_m = re.search(r"\b(?:at|in|for)\s+([A-Za-z][A-Za-z\s\-]{2,20})$", q)
    q_no_loc = q[:loc_m.start()] if loc_m else q

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
        loc_m = re.search(r"\b(?:at|in|for)\s+([A-Za-z][A-Za-z\s\-]{2,20})$", q)
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
    if m or "compliance" in q or "alert" in q:
        raw = check_tat_alert.invoke({
            "threshold_pct": float(m.group(1)) if m else 80.0, "period": period,
            "role": role, "db_name": db_name, "db_server": db_server,
            "db_user": db_user, "db_password": db_password,
        })
    else:
        raw = get_tat_compliance_dashboard.invoke({
            "period": period, "role": role, "db_name": db_name,
            "db_server": db_server, "db_user": db_user, "db_password": db_password,
        })
    return raw if isinstance(raw, str) else str(raw)


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
    return raw if isinstance(raw, str) else str(raw)


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

    # inline period — do NOT import agent.agent (circular)
    if "yesterday" in q:
        period = "yesterday"
    elif "last week" in q:
        period = "last_week"
    elif "this week" in q:
        period = "this_week"
    elif "last month" in q:
        period = "last_month"
    elif "this month" in q:
        period = "this_month"
    elif "this year" in q:
        period = "this_year"
    elif "today" in q:
        period = "today"
    else:
        period = "today"

    raw = get_department_dashboard.invoke({
        "department": dept,
        "period": period,
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