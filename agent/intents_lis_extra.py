"""
Extra LIS / Diagnostics intents, built from the stored-procedure fragments
(area / marketing-executive business report, temp-request search, bill test
lines, dispatch flags).

Wired in from agent/intents.py with ONE call at the bottom of that file:

    from agent.intents_lis_extra import build_extra_intents
    _INTENTS = build_extra_intents(sys.modules[__name__]) + _INTENTS

It receives the intents module itself (`base`) so it reuses the exact same
helpers (_conn, _period_dates, _list_card, _dashboard_card, _ALLOWED_ROLES,
and — importantly — the SAME _UnrecognizedPeriod class the dispatcher
catches). Nothing is imported at module level from intents.py, so there is
no circular import.

Design rules followed (same as the rest of intents.py):
  * fixed, parameterised SQL — no LLM call, zero token cost
  * a handler that cannot confidently answer returns None so the dispatcher
    moves on to the next intent and finally the LLM; this includes a named
    branch/area that could not be resolved and any SQL error
  * branches are resolved from THIS database's mstlocation — never from a
    hardcoded list
"""

import re
from datetime import date, timedelta

_base = None  # set by build_extra_intents()

_PHI_ROLES = ("admin", "reception")  # may see phone / address of a booking request

_GENERIC_LOC_TOKENS = {
    "branch", "centre", "center", "lab", "labs", "diagnostics", "diagnostic",
    "hospital", "clinic", "collection", "unit", "main", "road",
}

_MONTHS = ("january|february|march|april|may|june|july|august|september|"
           "october|november|december|jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec")

_DATEISH = re.compile(
    r"\b(\d{1,2}(st|nd|rd|th)?|20\d{2}|" + _MONTHS +
    r"|week|year|quarter|days?|ago|since|from|between|till|until)\w*\b"
)

_SCOPE_WORD = re.compile(
    r"\b(?:at|in|for)\s+(?!(?:the|all|each|every|this|last|today|yesterday|area|areas|"
    r"bill|bills|patient|user|executive|a|an|any|" + _MONTHS + r")\b)([a-z]{3,})"
)


# ----------------------------------------------------------------------
# shared helpers
# ----------------------------------------------------------------------

def _denied(role):
    if role in _base._ALLOWED_ROLES:
        return None
    return "Error: your role does not have access to this data."


def _money(x) -> str:
    return f"₹{float(x or 0):,.0f}"


def _period(q: str):
    """
    Period from the question. When the question names NO date-like word at
    all, default to This Month (the card always shows the period used, so it
    is never silent). When it names one we cannot parse, re-raise so the
    dispatcher falls through to the LLM instead of guessing.
    """
    try:
        return _base._period_dates(q)
    except _base._UnrecognizedPeriod:
        if _DATEISH.search(q):
            raise
        today = date.today()
        return today.replace(day=1).isoformat(), (today + timedelta(days=1)).isoformat(), "This Month"


def _locations(cursor):
    cursor.execute("SELECT LOCATIONID, LOCATIONNAME FROM mstlocation WHERE ACTIVE = 1")
    return [(r[0], str(r[1]).strip()) for r in cursor.fetchall() if r[1]]


def _resolve_location(q: str, locs):
    """
    ("none", None) | ("one", (id, name)) | ("many", [(id, name), ...]).
    Full branch name first (longest wins), then distinguishing name tokens.
    A token shared by most branches (e.g. the company name) is ignored.
    """
    ql = q.lower()
    full = [(lid, name) for lid, name in locs if re.search(rf"\b{re.escape(name.lower())}\b", ql)]
    if full:
        full.sort(key=lambda x: -len(x[1]))
        best = [x for x in full if len(x[1]) == len(full[0][1])]
        return ("one", best[0]) if len(best) == 1 else ("many", best)

    n = len(locs)
    owners_by_token = {}
    for lid, name in locs:
        for tok in set(re.findall(r"[a-z0-9]{4,}", name.lower())):
            if tok not in _GENERIC_LOC_TOKENS:
                owners_by_token.setdefault(tok, set()).add((lid, name))

    hits = set()
    for tok, owners in owners_by_token.items():
        if n > 2 and len(owners) > n / 2:
            continue
        if re.search(rf"\b{re.escape(tok)}\b", ql):
            hits |= owners
    if not hits:
        return ("none", None)
    hits = sorted(hits, key=lambda x: x[1])
    return ("one", hits[0]) if len(hits) == 1 else ("many", hits)


def _scope(q: str, cursor):
    """
    Returns (loc_id, loc_name, early_return).
    early_return is not None when the handler must stop and return it:
      * a message (several branches match)
      * the sentinel False  -> a place was named but not recognised -> return None
    """
    locs = _locations(cursor)
    status, found = _resolve_location(q, locs)
    if status == "one":
        return found[0], found[1], None
    if status == "many":
        return None, None, "Multiple branches match: " + ", ".join(n for _, n in found) + ". Please name one."
    if _SCOPE_WORD.search(q.lower()):
        return None, None, False
    return None, None, None


def _fail(label, exc):
    print(f"[intents_lis_extra] {label} failed, falling through to LLM: {type(exc).__name__}: {exc}")
    return None


# ----------------------------------------------------------------------
# 1. areas with referral business            (AREA1_ALL)
# ----------------------------------------------------------------------

def _h_area_list(q, role, db_name, db_server, db_user, db_password, matched_keyword=None):
    d = _denied(role)
    if d:
        return d
    date_from, date_to, label = _period(q)
    conn = _base._conn(db_name, db_server, db_user, db_password)
    if not conn:
        return "Error: could not connect to the database."
    try:
        cur = conn.cursor()
        loc_id, loc_name, early = _scope(q, cur)
        if early is False:
            return None
        if early:
            return early
        sql = ("SELECT DISTINCT C.AREAID, C.AREANAME FROM trninvlabpri PRI "
               "JOIN mstrefdoctor D ON PRI.REFDOCTCODE = D.DOCID "
               "JOIN mstarea C ON C.AREAID = D.AREACODE "
               "WHERE PRI.BILLDATE >= ? AND PRI.BILLDATE < ?")
        params = [date_from, date_to]
        if loc_id is not None:
            sql += " AND PRI.LOCATIONID = ?"
            params.append(loc_id)
        cur.execute(sql + " ORDER BY C.AREANAME", params)
        rows = cur.fetchall()
        where = f" · {loc_name}" if loc_name else " · All Branches"
        if not rows:
            return f"No areas with referral bills found ({label}{where})."
        return _base._list_card(
            icon="📍", title=f"Areas With Bills · {label}{where}",
            intro=f"{len(rows)} area{'s' if len(rows) != 1 else ''} had bills from referring doctors:",
            items=[{"primary": str(r[1])} for r in rows[:40]],
            footer=(f"Showing 40 of {len(rows)}." if len(rows) > 40 else None),
        )
    except Exception as e:
        return _fail("area_list", e)
    finally:
        conn.close()


# ----------------------------------------------------------------------
# 2. area-wise business                      (INV / AREA1 family)
# ----------------------------------------------------------------------

def _h_area_business(q, role, db_name, db_server, db_user, db_password, matched_keyword=None):
    d = _denied(role)
    if d:
        return d
    if re.search(r"\b(?:in|for|of)\s+(?:the\s+)?area\s+[a-z0-9]", q):
        return None  # a specific named area is not supported here — let the LLM handle it
    date_from, date_to, label = _period(q)
    conn = _base._conn(db_name, db_server, db_user, db_password)
    if not conn:
        return "Error: could not connect to the database."
    try:
        cur = conn.cursor()
        loc_id, loc_name, early = _scope(q, cur)
        if early is False:
            return None
        if early:
            return early

        loc_sql = " AND PRI.LOCATIONID = ?" if loc_id is not None else ""
        params = [date_from, date_to] + ([loc_id] if loc_id is not None else [])

        cur.execute(
            "SELECT C.AREAID, C.AREANAME, COUNT(DISTINCT PRI.BILLNO), SUM(ISNULL(det.CHARGE,0)), "
            "SUM(ISNULL(det.CONCESSION,0) + ISNULL(det.CONCESSION1,0)), SUM(ISNULL(det.REFUNDAMT,0)) "
            "FROM trninvlabpri PRI "
            "JOIN trninvlabdet det ON PRI.BILLNO = det.BILLNO "
            "JOIN mstrefdoctor D ON PRI.REFDOCTCODE = D.DOCID "
            "JOIN mstarea C ON C.AREAID = D.AREACODE "
            "WHERE PRI.BILLDATE >= ? AND PRI.BILLDATE < ?" + loc_sql +
            " GROUP BY C.AREAID, C.AREANAME ORDER BY SUM(ISNULL(det.CHARGE,0)) DESC",
            params,
        )
        rows = cur.fetchall()

        # Due is a BILL-level amount. Summing it over test lines would count it
        # once per test, so it is aggregated in its own query with no line join.
        cur.execute(
            "SELECT C.AREAID, SUM(ISNULL(PRI.CREDITAMOUNT,0)) FROM trninvlabpri PRI "
            "JOIN mstrefdoctor D ON PRI.REFDOCTCODE = D.DOCID "
            "JOIN mstarea C ON C.AREAID = D.AREACODE "
            "WHERE PRI.BILLDATE >= ? AND PRI.BILLDATE < ?" + loc_sql + " GROUP BY C.AREAID",
            params,
        )
        due_by_area = {r[0]: float(r[1] or 0) for r in cur.fetchall()}

        where = f" · {loc_name}" if loc_name else " · All Branches"
        if not rows:
            return f"No area-wise business found ({label}{where})."

        gross = sum(float(r[3] or 0) for r in rows)
        conc = sum(float(r[4] or 0) for r in rows)
        refund = sum(float(r[5] or 0) for r in rows)
        bills = sum(int(r[2] or 0) for r in rows)
        due = sum(due_by_area.values())

        items = []
        for area_id, name, nbills, g, c, rf in rows[:15]:
            g, c, rf = float(g or 0), float(c or 0), float(rf or 0)
            items.append({"primary": str(name), "fields": [
                f"{int(nbills or 0)} bills", f"Gross {_money(g)}", f"Concession {_money(c)}",
                f"Net billed {_money(g - c)}", f"Refund {_money(rf)}", f"Due {_money(due_by_area.get(area_id, 0))}",
            ]})
        return _base._list_card(
            icon="🗺️", title=f"Area-Wise Business · {label}{where}",
            intro=(f"{len(rows)} areas · {bills:,} bills · Gross {_money(gross)} · "
                   f"Net billed {_money(gross - conc)} · Refunds {_money(refund)} · Due {_money(due)}"),
            items=items,
            footer=("Net billed = gross − concession (not money collected). "
                    "Bills whose referring doctor has no area are not included."
                    + (f" Showing top 15 of {len(rows)} areas." if len(rows) > 15 else "")),
        )
    except Exception as e:
        return _fail("area_business", e)
    finally:
        conn.close()


# ----------------------------------------------------------------------
# 3. marketing-executive-wise business       (INV_ALL_USER family)
# ----------------------------------------------------------------------

def _h_exec_business(q, role, db_name, db_server, db_user, db_password, matched_keyword=None):
    d = _denied(role)
    if d:
        return d
    date_from, date_to, label = _period(q)
    conn = _base._conn(db_name, db_server, db_user, db_password)
    if not conn:
        return "Error: could not connect to the database."
    try:
        cur = conn.cursor()
        loc_id, loc_name, early = _scope(q, cur)
        if early is False:
            return None
        if early:
            return early

        loc_sql = " AND PRI.LOCATIONID = ?" if loc_id is not None else ""
        params = [date_from, date_to] + ([loc_id] if loc_id is not None else [])
        join = ("JOIN mstrefdoctor D ON PRI.REFDOCTCODE = D.DOCID "
                "JOIN trnmarkrefdrmapping A ON A.DOCID = D.DOCID "
                "JOIN mstusers B ON A.NAMEID = B.ID ")

        cur.execute(
            "SELECT B.ID, B.USERID, COUNT(DISTINCT PRI.BILLNO), SUM(ISNULL(det.CHARGE,0)), "
            "SUM(ISNULL(det.CONCESSION,0) + ISNULL(det.CONCESSION1,0)), SUM(ISNULL(det.REFUNDAMT,0)) "
            "FROM trninvlabpri PRI JOIN trninvlabdet det ON PRI.BILLNO = det.BILLNO " + join +
            "WHERE PRI.BILLDATE >= ? AND PRI.BILLDATE < ?" + loc_sql +
            " GROUP BY B.ID, B.USERID ORDER BY SUM(ISNULL(det.CHARGE,0)) DESC",
            params,
        )
        rows = cur.fetchall()

        cur.execute(
            "SELECT B.ID, SUM(ISNULL(PRI.CREDITAMOUNT,0)) FROM trninvlabpri PRI " + join +
            "WHERE PRI.BILLDATE >= ? AND PRI.BILLDATE < ?" + loc_sql + " GROUP BY B.ID",
            params,
        )
        due_by_user = {r[0]: float(r[1] or 0) for r in cur.fetchall()}

        where = f" · {loc_name}" if loc_name else " · All Branches"
        if not rows:
            return f"No marketing-executive business found ({label}{where})."

        items = []
        for uid, userid, nbills, g, c, rf in rows[:15]:
            g, c, rf = float(g or 0), float(c or 0), float(rf or 0)
            items.append({"primary": str(userid), "fields": [
                f"{int(nbills or 0)} bills", f"Gross {_money(g)}", f"Net billed {_money(g - c)}",
                f"Refund {_money(rf)}", f"Due {_money(due_by_user.get(uid, 0))}",
            ]})
        return _base._list_card(
            icon="🧑‍💼", title=f"Business By Marketing Executive · {label}{where}",
            intro=f"{len(rows)} executive{'s' if len(rows) != 1 else ''} with mapped referring doctors:",
            items=items,
            footer=("Only referring doctors mapped to a marketing executive are included. A doctor mapped "
                    "to more than one executive is counted under each, so these rows should not be added up."
                    + (f" Showing top 15 of {len(rows)}." if len(rows) > 15 else "")),
        )
    except Exception as e:
        return _fail("exec_business", e)
    finally:
        conn.close()


# ----------------------------------------------------------------------
# 4. doctors mapped to a marketing executive
# ----------------------------------------------------------------------

_USER_STOP = {"wise", "business", "for", "by", "this", "last", "today", "yesterday", "all",
              "the", "with", "who", "which", "how", "many", "mapped", "doctors", "doctor"}


def _h_exec_doctors(q, role, db_name, db_server, db_user, db_password, matched_keyword=None):
    d = _denied(role)
    if d:
        return d
    m = re.search(r"\b(?:user|executive|exec)\s+(?:named\s+|id\s+)?([a-z0-9_.@-]{2,})", q)
    userid = m.group(1) if m and m.group(1) not in _USER_STOP else None

    conn = _base._conn(db_name, db_server, db_user, db_password)
    if not conn:
        return "Error: could not connect to the database."
    try:
        cur = conn.cursor()
        if userid:
            cur.execute(
                "SELECT D.DOCNAME, C.AREANAME FROM trnmarkrefdrmapping A "
                "JOIN mstusers B ON A.NAMEID = B.ID "
                "JOIN mstrefdoctor D ON A.DOCID = D.DOCID "
                "LEFT JOIN mstarea C ON C.AREAID = D.AREACODE "
                "WHERE UPPER(B.USERID) = ? ORDER BY D.DOCNAME",
                [userid.upper()],
            )
            rows = cur.fetchall()
            if not rows:
                return f"No referring doctors are mapped to '{userid}'."
            return _base._list_card(
                icon="🧑‍💼", title=f"Doctors Mapped To {userid}",
                intro=f"{len(rows)} referring doctor{'s' if len(rows) != 1 else ''}:",
                items=[{"primary": str(r[0]), "fields": ([f"Area: {r[1]}"] if r[1] else [])} for r in rows[:30]],
                footer=(f"Showing 30 of {len(rows)}." if len(rows) > 30 else None),
            )

        cur.execute(
            "SELECT B.USERID, COUNT(DISTINCT A.DOCID) FROM trnmarkrefdrmapping A "
            "JOIN mstusers B ON A.NAMEID = B.ID GROUP BY B.USERID ORDER BY COUNT(DISTINCT A.DOCID) DESC"
        )
        rows = cur.fetchall()
        if not rows:
            return "No referring doctors are mapped to any marketing executive."
        return _base._list_card(
            icon="🧑‍💼", title="Marketing Executives — Mapped Doctors",
            intro=f"{len(rows)} executives. Ask \"doctors mapped to user <id>\" to see one list.",
            items=[{"primary": str(r[0]), "fields": [f"{int(r[1])} doctors"]} for r in rows[:25]],
            footer=(f"Showing 25 of {len(rows)}." if len(rows) > 25 else None),
        )
    except Exception as e:
        return _fail("exec_doctors", e)
    finally:
        conn.close()


# ----------------------------------------------------------------------
# 5. tests on a bill with charge / concession / refund   (GetInvDtls)
# ----------------------------------------------------------------------

def _h_bill_test_lines(q, role, db_name, db_server, db_user, db_password, matched_keyword=None):
    d = _denied(role)
    if d:
        return d
    m = re.search(r"\b(?:bill\s*(?:no\.?|number)?\s*[:\-]?\s*)?([A-Z]{2,4}\d{3,})\b", q.upper())
    if not m:
        return None
    billno = m.group(1).upper()
    conn = _base._conn(db_name, db_server, db_user, db_password)
    if not conn:
        return "Error: could not connect to the database."
    try:
        cur = conn.cursor()
        cur.execute("SELECT NAME, BILLDATE, CREDITAMOUNT FROM trninvlabpri WHERE BILLNO = ?", [billno])
        head = cur.fetchone()
        if not head:
            return f"No bill found with number {billno}."
        # Cancelled lines (STATUS = 'C') are excluded, exactly as the report SP's GetInvDtls does.
        cur.execute(
            "SELECT I.INVNAME, det.CHARGE, ISNULL(det.CONCESSION,0) + ISNULL(det.CONCESSION1,0), "
            "ISNULL(det.REFUNDAMT,0) FROM trninvlabdet det "
            "JOIN mstinvestigations I ON det.TCODE = I.INVCODE "
            "WHERE det.BILLNO = ? AND ISNULL(det.STATUS,'') <> 'C'",
            [billno],
        )
        rows = cur.fetchall()
        if not rows:
            return f"Bill {billno} has no active (non-cancelled) tests."
        gross = sum(float(r[1] or 0) for r in rows)
        conc = sum(float(r[2] or 0) for r in rows)
        refund = sum(float(r[3] or 0) for r in rows)
        return _base._list_card(
            icon="🧾", title=f"Tests On Bill {billno}",
            intro=f"{head[0]} · {head[1]}",
            items=[{"primary": str(r[0]), "fields": [
                f"Charge {_money(r[1])}",
                *([f"Concession {_money(r[2])}"] if float(r[2] or 0) else []),
                *([f"Refund {_money(r[3])}"] if float(r[3] or 0) else []),
            ]} for r in rows[:25]],
            footer=(f"{len(rows)} tests · Gross {_money(gross)} · Concession {_money(conc)} · "
                    f"Net billed {_money(gross - conc)} · Refund {_money(refund)} · Bill due {_money(head[2])}"),
        )
    except Exception as e:
        return _fail("bill_test_lines", e)
    finally:
        conn.close()


# ----------------------------------------------------------------------
# 6. bills that came from a pre-booking / temp request   (SearchDate / SearchName)
# ----------------------------------------------------------------------

_NAME_STOP = {"this", "last", "today", "yesterday", "all", "each", "every", "the", "a", "an", "me", "us", "any"}


def _extract_patient_name(q: str):
    m = re.search(
        r"(?:named|name|patient|for)\s+([a-z][a-z .'-]{1,40}?)(?=\s+(?:today|yesterday|this|last|at|in|on|from)\b|$)", q)
    if not m:
        return None
    name = m.group(1).strip()
    if len(name) < 3 or name.split()[0] in _NAME_STOP:
        return None
    return name


def _h_prebooked_bills(q, role, db_name, db_server, db_user, db_password, matched_keyword=None):
    d = _denied(role)
    if d:
        return d
    date_from, date_to, label = _period(q)
    name = _extract_patient_name(q)
    conn = _base._conn(db_name, db_server, db_user, db_password)
    if not conn:
        return "Error: could not connect to the database."
    try:
        cur = conn.cursor()
        loc_id, loc_name, early = _scope(q, cur)
        if early is False:
            # the "for <word>" may simply be the patient name — only bail out if it was not
            if not name:
                return None
        elif early:
            return early

        where_sql = ("WHERE BILLDATE >= ? AND BILLDATE < ? AND TEMPID IS NOT NULL AND TEMPID <> ''")
        params = [date_from, date_to]
        if loc_id is not None:
            where_sql += " AND LOCATIONID = ?"
            params.append(loc_id)
        if name:
            where_sql += " AND NAME LIKE ?"
            params.append(f"%{name}%")

        cur.execute("SELECT COUNT(*) FROM trninvlabpri " + where_sql, params)
        total = int(cur.fetchone()[0] or 0)
        where = f" · {loc_name}" if loc_name else " · All Branches"
        who = f" · '{name}'" if name else ""
        if not total:
            return f"No bills from pre-booked requests found ({label}{where}{who})."

        cur.execute("SELECT TOP 20 TEMPID, BILLDATE, NAME, BILLNO FROM trninvlabpri "
                    + where_sql + " ORDER BY ID DESC", params)
        rows = cur.fetchall()
        return _base._list_card(
            icon="📝", title=f"Bills From Pre-Booked Requests · {label}{where}{who}",
            intro=f"{total:,} bill{'s' if total != 1 else ''} were created from a booking request (TempID):",
            items=[{"primary": str(r[2]), "fields": [f"Bill {r[3]}", f"TempID {r[0]}", str(r[1])]} for r in rows],
            footer=(f"Showing latest 20 of {total:,}." if total > 20 else None),
        )
    except Exception as e:
        return _fail("prebooked_bills", e)
    finally:
        conn.close()


# ----------------------------------------------------------------------
# 7. one booking request in full                          (GetPatDtls_TempID)
# ----------------------------------------------------------------------

_ID_STOP = {"for", "of", "the", "details", "detail", "info", "no", "number", "id"}


def _h_prebooking_detail(q, role, db_name, db_server, db_user, db_password, matched_keyword=None):
    d = _denied(role)
    if d:
        return d
    m = re.search(
        r"(?:temp\s*id|tempid|request\s*(?:no\.?|number|id)|req\s*no\.?|booking\s*(?:no\.?|id|number)|details\s+of\s+request)"
        r"\s*[:#\-]?\s*([a-z0-9][a-z0-9\-_/]{2,})", q)
    if not m or m.group(1) in _ID_STOP:
        return None
    tempid = m.group(1).upper()
    can_see_phi = role in _PHI_ROLES

    conn = _base._conn(db_name, db_server, db_user, db_password)
    if not conn:
        return "Error: could not connect to the database."
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT A.NAME, A.AGE, A.AGETYPE, A.ADDRESS, A.PHONE, B.SALUTATION, C.DOCNAME, A.GENDER, "
            "E.INVNAME, D.RATE, A.[DATE], E.ISPACKAGE "
            "FROM trntempinvpri A "
            "LEFT JOIN mstsalutation B ON A.SALUTATION = B.ID "
            "LEFT JOIN mstrefdoctor C ON A.REFDOCID = C.DOCID "
            "JOIN trntempinvdet D ON A.TEMPID = D.TEMPID "
            "JOIN mstinvestigations E ON D.INVCODE = E.INVCODE "
            "WHERE A.TEMPID = ?",
            [tempid],
        )
        rows = cur.fetchall()
        if not rows:
            return f"No booking request found with TempID {tempid}."

        name, age, agetype, address, phone, sal, doc, gender, _, _, when, _ = rows[0]
        who = " ".join(x for x in (str(sal or "").strip(), str(name or "").strip()) if x)
        bits = [who]
        if age not in (None, ""):
            bits.append(f"{age}{(' ' + str(agetype)) if isinstance(agetype, str) and agetype.strip() and not agetype.strip().isdigit() else ''}")
        if gender:
            bits.append(str(gender))
        if doc:
            bits.append(f"Ref: {doc}")
        if when:
            bits.append(str(when))
        if can_see_phi:
            if phone:
                bits.append(f"Phone: {phone}")
            if address:
                bits.append(f"Address: {address}")
        total = sum(float(r[9] or 0) for r in rows)
        return _base._list_card(
            icon="📝", title=f"Booking Request {tempid}",
            intro=" · ".join(bits),
            items=[{"primary": str(r[8]), "fields": [_money(r[9]), *(["Package"] if r[11] else [])]} for r in rows[:25]],
            footer=f"{len(rows)} test{'s' if len(rows) != 1 else ''} · Total {_money(total)}"
                   + ("" if can_see_phi else " · Phone and address are visible to admin and reception only."),
        )
    except Exception as e:
        return _fail("prebooking_detail", e)
    finally:
        conn.close()


# ----------------------------------------------------------------------
# 8. pre-booking numbers
# ----------------------------------------------------------------------

def _h_prebooking_summary(q, role, db_name, db_server, db_user, db_password, matched_keyword=None):
    d = _denied(role)
    if d:
        return d
    date_from, date_to, label = _period(q)
    conn = _base._conn(db_name, db_server, db_user, db_password)
    if not conn:
        return "Error: could not connect to the database."
    try:
        cur = conn.cursor()
        locs = _locations(cur)
        status, _found = _resolve_location(q, locs)
        if status != "none" or _SCOPE_WORD.search(q.lower()):
            return None  # branch-level pre-booking numbers are not supported here

        cur.execute("SELECT COUNT(*) FROM trntempinvpri WHERE [DATE] >= ? AND [DATE] < ?", [date_from, date_to])
        requests_created = int(cur.fetchone()[0] or 0)
        cur.execute("SELECT COUNT(*), COUNT(DISTINCT TEMPID) FROM trninvlabpri "
                    "WHERE BILLDATE >= ? AND BILLDATE < ? AND TEMPID IS NOT NULL AND TEMPID <> ''",
                    [date_from, date_to])
        row = cur.fetchone()
        bills, distinct_requests = int(row[0] or 0), int(row[1] or 0)
        return _base._dashboard_card(
            icon="📝", title="Pre-Booking Summary", subtitle=label,
            meta=[{"icon": "📍", "text": "All Branches"}],
            stats=[
                {"label": "REQUESTS CREATED", "value": f"{requests_created:,}"},
                {"label": "BILLS FROM A REQUEST", "value": f"{bills:,}"},
                {"label": "DISTINCT REQUESTS BILLED", "value": f"{distinct_requests:,}"},
            ],
            footer={"label": "Note",
                    "value": "Requests created and bills raised are counted by their own dates, so they are not a conversion rate."},
        )
    except Exception as e:
        return _fail("prebooking_summary", e)
    finally:
        conn.close()


# ----------------------------------------------------------------------
# 9. organisations / doctors set to hold reports for dispatch
# ----------------------------------------------------------------------

def _h_dispatch_accounts(q, role, db_name, db_server, db_user, db_password, matched_keyword=None):
    d = _denied(role)
    if d:
        return d
    want_orgs = "doctor" not in q
    want_docs = "organi" not in q and "client" not in q
    if not want_orgs and not want_docs:
        want_orgs = want_docs = True
    conn = _base._conn(db_name, db_server, db_user, db_password)
    if not conn:
        return "Error: could not connect to the database."
    try:
        cur = conn.cursor()
        items, parts = [], []
        if want_orgs:
            cur.execute("SELECT ORGANISATIONNAME FROM mstorganisation WHERE DISPATCH = 'TRUE' ORDER BY ORGANISATIONNAME")
            orgs = cur.fetchall()
            parts.append(f"{len(orgs)} organisation{'s' if len(orgs) != 1 else ''}")
            items += [{"primary": str(r[0]), "fields": ["Organisation"]} for r in orgs[:15]]
        if want_docs:
            cur.execute("SELECT DOCNAME FROM mstrefdoctor WHERE DISPATCH = 'TRUE' ORDER BY DOCNAME")
            docs = cur.fetchall()
            parts.append(f"{len(docs)} referring doctor{'s' if len(docs) != 1 else ''}")
            items += [{"primary": str(r[0]), "fields": ["Referring doctor"]} for r in docs[:15]]
        if not items:
            return "No organisations or referring doctors are set to dispatch."
        return _base._list_card(
            icon="📦", title="Dispatch Accounts",
            intro=" · ".join(parts) + " set to hold reports for dispatch:",
            items=items,
            footer="Showing up to 15 of each.",
        )
    except Exception as e:
        return _fail("dispatch_accounts", e)
    finally:
        conn.close()


# ----------------------------------------------------------------------
# registry — most specific first; placed in front of the existing list
# ----------------------------------------------------------------------

def build_extra_intents(base):
    global _base
    _base = base
    return [
        # "doctors mapped to user X" must beat the executive-business entry below
        (["doctors mapped", "mapped doctors", "doctors under", "doctors of executive",
          "doctors handled by", "doctors assigned to"], _h_exec_doctors),
        (["marketing executive", "business by executive", "executive wise", "executive-wise",
          "business by user", "user wise business", "marketing user"], _h_exec_business),
        (["area wise", "area-wise", "areawise", "business by area", "billing by area",
          "revenue by area", "business per area"], _h_area_business),
        (["which areas", "list areas", "areas with bills", "areas with referrals",
          "active areas", "area list"], _h_area_list),
        (["test charges", "charges for bill", "charges on bill", "tests on bill", "tests billed on",
          "concession on bill", "refund on bill", "billed tests", "test wise charges"], _h_bill_test_lines),
        (["temp id", "tempid", "request no", "request number", "booking request",
          "request id", "details of request"], _h_prebooking_detail),
        (["how many pre booking", "how many pre-booking", "how many prebooking",
          "pre booking summary", "pre-booking summary", "prebooking summary",
          "pre booking count", "pre-booking count", "prebooking count"], _h_prebooking_summary),
        (["pre booked", "pre-booked", "prebooked", "pre booking bills", "pre-booking bills",
          "prebooking bills", "advance booking"], _h_prebooked_bills),
        (["dispatch accounts", "dispatch organisations", "dispatch organizations", "dispatch doctors",
          "which organisations dispatch", "which doctors dispatch", "reports held for dispatch",
          "dispatch list", "dispatch enabled"], _h_dispatch_accounts),
    ]