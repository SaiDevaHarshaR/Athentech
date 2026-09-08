from datetime import datetime, timedelta
"""
Curated, hand-verified queries for the small number of questions that
kept failing when left to the LLM to write fresh SQL for every time.

This is NOT the same as the flexible describe_table/run_sql_query
agent — these functions contain FIXED, TESTED SQL patterns confirmed
correct against real production data (see the column/table choices
below, each confirmed via real console logs during debugging). The
agent's job for a question that matches one of these is just to call
the function and format the result — not to write the SQL.

Add a new function here only once a pattern has been CONFIRMED correct
against real data (not "probably right") — this file's whole value is
that its contents are certain, unlike the general agent's guesses.
"""

import re
from datetime import date, timedelta

from database.connection import get_hospital_connection


def resolve_relative_date(value: str) -> str:
    """
    Converts a relative date keyword to a real YYYY-MM-DD string using
    the ACTUAL server clock (datetime.now()) — never the caller's own
    idea of what "today" is. This exists because an LLM asked to
    convert "yesterday" into a literal date will use its own internal
    sense of the current date, which can be badly stale (anchored near
    its training cutoff, not the real current date) — a real bug found
    in production: "yesterday" was resolved to a date years in the
    past. Explicit YYYY-MM-DD values pass through unchanged.
    """
    if re.match(r"^\d{4}-\d{2}-\d{2}$", value):
        return value

    today = date.today()
    keyword = value.strip().lower()

    if keyword == "today":
        return today.isoformat()
    if keyword == "yesterday":
        return (today - timedelta(days=1)).isoformat()
    if keyword in ("this_month_start", "this month"):
        return today.replace(day=1).isoformat()
    if keyword in ("this_year_start", "this year"):
        return today.replace(month=1, day=1).isoformat()

    raise ValueError(
        f"Unrecognized date value '{value}' — use YYYY-MM-DD, 'today', "
        "'yesterday', 'this_month_start', or 'this_year_start'."
    )


def resolve_location_id(location_keyword: str, db_name: str, db_server=None, db_user=None, db_password=None):
    """
    Resolves a location keyword to its real LOCATIONID code (format
    'LOC04' etc.) using trntempdaycollall, which has both the location
    NAME and its real ID code together — no join needed.

    IMPORTANT HISTORY: an earlier version of this function used
    mstlocationusers.UserId, based on a real console log where
    "Kompally" appeared to resolve correctly. That was wrong —
    mstlocationusers turned out to be a STAFF/USER ACCOUNTS table
    (real column contents: "DR.G.VIJAY RAMREDDY", "KM", etc. — people's
    names), not a locations table. The earlier match was very likely a
    staff member's name coincidentally containing the search keyword,
    not an actual location — meaning every query using that resolved ID
    was filtering by an essentially arbitrary wrong number. Confirmed
    via a full unfiltered dump of the table's real contents.
    """
    conn = get_hospital_connection(db_name, db_server, db_user, db_password)
    if not conn:
        return None, None
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT DISTINCT LOCATIONID, LOCATION FROM trntempdaycollall WHERE LOCATION LIKE ?",
            (f"%{location_keyword}%",)
        )
        rows = cursor.fetchall()
        if not rows:
            return None, None
        if len(rows) > 1:
            # Before treating this as genuinely ambiguous, check for an
            # exact (case-insensitive) match — e.g. "Kukatpally" matches
            # both "Kukatpally" and "Spinova-Kukatpally" via LIKE, but
            # if the user said exactly "Kukatpally", that's not actually
            # ambiguous, it's a precise match plus a coincidental extra
            # substring hit. Only ask the user when there's no single
            # best answer.
            exact_matches = [r for r in rows if r[1].strip().lower() == location_keyword.strip().lower()]
            if len(exact_matches) == 1:
                return exact_matches[0][0], exact_matches[0][1]
            return "AMBIGUOUS", [r[1] for r in rows]
        return rows[0][0], rows[0][1]
    finally:
        conn.close()


def get_day_collection(
    location_keyword: str,
    date_from: str,
    date_to: str,
    db_name: str,
    db_server=None, db_user=None, db_password=None,
) -> dict:
    """
    Day collection query for one location and one date range.

    HONEST CAVEAT, not yet fully verified: this resolves the location
    via trntempdaycollall (which pairs a real LOCATION name with its
    LOCATIONID code, e.g. 'LOC04') and then uses that same LOCATIONID
    value to filter trnmodeofcollectionsdet. This assumes both tables
    use the SAME LOCATIONID scheme — that has NOT been independently
    confirmed. If results still look wrong after this fix, the next
    thing to check is whether trnmodeofcollectionsdet.LOCATIONID is
    actually a different kind of ID (e.g. one referencing
    mstlocationusers.Id — a staff/user ID — rather than a location
    code) by looking at its real raw values directly for a date range
    already confirmed to have data.

    date_from/date_to accept 'YYYY-MM-DD' or 'today'/'yesterday'/
    'this_month_start'/'this_year_start' (resolved server-side, never
    trust the caller's own date math — see resolve_relative_date).
    """
    try:
        date_from = resolve_relative_date(date_from)
        date_to = resolve_relative_date(date_to)
    except ValueError as e:
        print(f"[get_day_collection] FAILED date resolution: {e}")
        return {"error": str(e)}

    print(f"[get_day_collection] keyword='{location_keyword}' resolved dates: {date_from} to {date_to}")

    location_id, matched = resolve_location_id(location_keyword, db_name, db_server, db_user, db_password)
    print(f"[get_day_collection] location resolution: id={location_id!r} matched={matched!r}")

    if location_id is None:
        return {"error": f"No location found matching '{location_keyword}'."}
    if location_id == "AMBIGUOUS":
        return {"ambiguous": True, "candidates": matched}

    conn = get_hospital_connection(db_name, db_server, db_user, db_password)
    if not conn:
        return {"error": "Could not connect to the hospital database."}

    try:
        cursor = conn.cursor()
start = datetime.strptime(date_from[:10], "%Y-%m-%d")
        end_exclusive = datetime.strptime(date_to[:10], "%Y-%m-%d") + timedelta(days=1)
        date_from_param = start.strftime("%Y-%m-%d")
        date_to_param = end_exclusive.strftime("%Y-%m-%d")

        query = """
            SELECT MODE, SUM(PAIDAMOUNT) AS TotalAmount
            FROM trnmodeofcollectionsdet
            WHERE LOCATIONID = ?
            AND DATEOFBILL >= ?
            AND DATEOFBILL < ?
            GROUP BY MODE
            """
        print(
            f"[get_day_collection] SQL: {query.strip()} | "
            f"params: ({location_id!r}, {date_from_param!r}, {date_to_param!r})"
        )
        cursor.execute(query, (location_id, date_from_param, date_to_param))
        rows = cursor.fetchall()
        print(f"[get_day_collection] returned {len(rows)} row(s)")
    finally:
        conn.close()

    if not rows:
        return {
            "location": matched,
            "location_id": location_id,
            "date_from": date_from,
            "date_to": date_to,
            "no_data": True,
        }

    breakdown = [{"mode": r[0], "amount": float(r[1]) if r[1] is not None else None} for r in rows]
    print(f"[get_day_collection] raw rows: {[(r[0], r[1]) for r in rows]}")
    # If PAIDAMOUNT summed to NULL (not a real 0), that's a genuinely
    # different situation from "really collected zero" — could mean
    # those transactions have a null amount rather than a zero one,
    # which is worth surfacing honestly rather than silently coalescing
    # to a plain 0.00 as if it were the same thing.
    had_null_amounts = any(b["amount"] is None for b in breakdown)
    breakdown = [{"mode": b["mode"], "amount": b["amount"] or 0.0} for b in breakdown]
    total = sum(b["amount"] for b in breakdown)

    return {
        "location": matched,
        "location_id": location_id,
        "date_from": date_from,
        "date_to": date_to,
        "had_null_amounts": had_null_amounts,
        "total": total,
        "breakdown": breakdown,
    }