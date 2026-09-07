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

from database.connection import get_hospital_connection


def resolve_location_id(location_keyword: str, db_name: str, db_server=None, db_user=None, db_password=None):
    """
    Confirmed pattern: mstlocationusers.UserId holds the location NAME
    (not Id, which is a numeric key — confirmed via a real SQL type
    error when that was tried instead). Returns (id, matched_name) for
    the best match, or (None, None) if nothing matched.
    """
    conn = get_hospital_connection(db_name, db_server, db_user, db_password)
    if not conn:
        return None, None
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT TOP 5 Id, UserId FROM mstlocationusers WHERE UserId LIKE ?",
            (f"%{location_keyword}%",)
        )
        rows = cursor.fetchall()
        if not rows:
            return None, None
        if len(rows) > 1:
            # Ambiguous — more than one location matched this keyword.
            # Don't silently pick one; the caller needs to know this.
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
    Confirmed-correct day collection query for one location and one
    date range. date_from/date_to must be 'YYYY-MM-DD' strings.

    Returns a dict ready to hand to the dashboard-card renderer, or an
    "error"/"ambiguous" key explaining what went wrong instead of
    silently returning zeros.
    """
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", date_from) or not re.match(r"^\d{4}-\d{2}-\d{2}$", date_to):
        return {"error": "date_from and date_to must be YYYY-MM-DD"}

    location_id, matched = resolve_location_id(location_keyword, db_name, db_server, db_user, db_password)

    if location_id is None:
        return {"error": f"No location found matching '{location_keyword}'."}
    if location_id == "AMBIGUOUS":
        return {"ambiguous": True, "candidates": matched}

    conn = get_hospital_connection(db_name, db_server, db_user, db_password)
    if not conn:
        return {"error": "Could not connect to the hospital database."}

    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT MODE, SUM(PAIDAMOUNT) AS TotalAmount
            FROM trnmodeofcollectionsdet
            WHERE LOCATIONID = ?
            AND DATEOFBILL >= ?
            AND DATEOFBILL <= ?
            GROUP BY MODE
            """,
            (location_id, date_from, date_to)
        )
        rows = cursor.fetchall()
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

    breakdown = [{"mode": r[0], "amount": float(r[1] or 0)} for r in rows]
    total = sum(b["amount"] for b in breakdown)

    return {
        "location": matched,
        "location_id": location_id,
        "date_from": date_from,
        "date_to": date_to,
        "total": total,
        "breakdown": breakdown,
    }