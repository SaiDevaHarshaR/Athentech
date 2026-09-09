"""
Curated, hand-verified queries for questions that kept failing when
left to the LLM to write fresh SQL every time.
"""

import re
from datetime import date, datetime, timedelta

from database.connection import get_hospital_connection


def resolve_relative_date(value: str) -> str:
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
    conn = get_hospital_connection(db_name, db_server, db_user, db_password)
    if not conn:
        return None, None
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT DISTINCT LOCATIONID, LOCATION FROM trntempdaycollall WHERE LOCATION LIKE ?",
            (f"%{location_keyword}%",),
        )
        rows = cursor.fetchall()
        if not rows:
            return None, None
        if len(rows) > 1:
            exact_matches = [
                r for r in rows
                if r[1].strip().lower() == location_keyword.strip().lower()
            ]
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
    db_server=None,
    db_user=None,
    db_password=None,
) -> dict:
    try:
        date_from = resolve_relative_date(date_from)
        date_to = resolve_relative_date(date_to)
    except ValueError as e:
        print(f"[get_day_collection] FAILED date resolution: {e}")
        return {"error": str(e)}

    print(f"[get_day_collection] keyword='{location_keyword}' resolved dates: {date_from} to {date_to}")

    location_id, matched = resolve_location_id(
        location_keyword, db_name, db_server, db_user, db_password
    )
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

    breakdown = [
        {"mode": r[0], "amount": float(r[1]) if r[1] is not None else None}
        for r in rows
    ]
    print(f"[get_day_collection] raw rows: {[(r[0], r[1]) for r in rows]}")

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