"""
TAT Compliance dashboard — REBUILT to use trnInvStatus's real
per-stage clinical timestamps (SAMPLECOLLECTEDDATE, RESULTENTRYDATE)
instead of trnparamresult.BILLDATE/CREATEDATE, which was confirmed to
be the wrong measurement window: BILLDATE reflects billing/order time,
not actual sample collection — using it as the TAT start point
systematically inflates every measured TAT (a patient can be billed
well before their sample is physically drawn). This was the likely
cause of implausible 100%-delayed results seen using the old version.

Real TAT here = SAMPLECOLLECTEDDATE (when the sample was physically
collected) to RESULTENTRYDATE (when the lab entered the result) — the
genuine clinical processing window, both confirmed real columns on
trnInvStatus.

Department filtering is intentionally NOT implemented — same root
cause as the previous version: mstInvestigations.DEPARTMENTID does not
match any confirmed department/sub-department table, and trnInvStatus's
own DEPTCODE has not been independently verified against
mstsubdepartment either. Don't add it back without checking that first.

Location filtering works via trninvlabdet.LOCATIONID, joined on
BILLNO (trnInvStatus itself has no LOCATIONID column).
"""

import re

from database.connection import get_hospital_connection


def get_tat_compliance_dashboard(
    period: str,
    db_name: str,
    db_server=None, db_user=None, db_password=None,
    specific_date: str = None,
    location_id: str = None,
) -> dict:
    """
    period: 'today' | 'yesterday' | 'this_week' | 'this_month' | 'day'
      (use period='day' with specific_date='YYYY-MM-DD' for one exact date)
    IMPORTANT (confirmed real bug, now fixed): the period is scoped by
    RESULTENTRYDATE (when the test was actually completed), NOT
    BILLDATE (when it was ordered/billed). Filtering by BILLDATE while
    requiring a completed result caused a real bug — "yesterday" almost
    always returned zero, since a test billed yesterday typically isn't
    completed (both SAMPLECOLLECTEDDATE and RESULTENTRYDATE filled)
    until today or later. Completion date is the correct anchor for
    "how did we perform on tests completed in period X".
    location_id: a real LOC0X code (resolved one layer up, same pattern
    as get_lab_day_collection), or None for all locations combined.
    """
    if period == "day":
        if not specific_date or not re.match(r"^\d{4}-\d{2}-\d{2}$", specific_date):
            return {"error": f"period='day' requires a real specific_date (YYYY-MM-DD), got '{specific_date}'."}
        date_sql = f"s.RESULTENTRYDATE >= '{specific_date}' AND s.RESULTENTRYDATE < DATEADD(DAY, 1, CAST('{specific_date}' AS DATE))"
        period_label = specific_date
    elif period == "today":
        date_sql = "s.RESULTENTRYDATE >= CAST(GETDATE() AS DATE) AND s.RESULTENTRYDATE < DATEADD(DAY, 1, CAST(GETDATE() AS DATE))"
        period_label = "Today"
    elif period == "yesterday":
        date_sql = (
            "s.RESULTENTRYDATE >= CAST(DATEADD(DAY, -1, GETDATE()) AS DATE) "
            "AND s.RESULTENTRYDATE < CAST(GETDATE() AS DATE)"
        )
        period_label = "Yesterday"
    elif period == "this_week":
        date_sql = (
            "s.RESULTENTRYDATE >= DATEADD(DAY, 1-DATEPART(WEEKDAY, GETDATE()), CAST(GETDATE() AS DATE)) "
            "AND s.RESULTENTRYDATE < DATEADD(DAY, 1, CAST(GETDATE() AS DATE))"
        )
        period_label = "This Week"
    elif period == "this_month":
        date_sql = (
            "s.RESULTENTRYDATE >= DATEADD(MONTH, DATEDIFF(MONTH, 0, GETDATE()), 0) "
            "AND s.RESULTENTRYDATE < DATEADD(MONTH, DATEDIFF(MONTH, 0, GETDATE()) + 1, 0)"
        )
        period_label = "This Month"
    else:
        return {"error": f"Unsupported period '{period}'."}

    loc_sql = ""
    if location_id:
        loc_sql = f"AND l.LOCATIONID = '{location_id}' "

    expected_tat_expr = (
        "CASE "
        "WHEN inv.TATTYPE = 'Hours' THEN TRY_CAST(inv.TATTIME AS INT) * 60 "
        "WHEN inv.TATTYPE = 'Days' THEN TRY_CAST(inv.TATTIME AS INT) * 1440 "
        "ELSE NULL END"
    )
    actual_tat_expr = (
        "CAST(CASE WHEN DATEDIFF(MINUTE, s.SAMPLECOLLECTEDDATE, s.RESULTENTRYDATE) BETWEEN 0 AND 10080 "
        "THEN DATEDIFF(MINUTE, s.SAMPLECOLLECTEDDATE, s.RESULTENTRYDATE) END AS BIGINT)"
    )

    where_common = (
        f"WHERE {date_sql} {loc_sql}"
        "AND s.SAMPLECOLLECTEDDATE IS NOT NULL AND s.RESULTENTRYDATE IS NOT NULL "
        f"AND inv.TATTIME IS NOT NULL AND inv.TATTYPE IS NOT NULL "
        f"AND {actual_tat_expr} IS NOT NULL"
    )

    conn = get_hospital_connection(db_name, db_server, db_user, db_password)
    if not conn:
        return {"error": "Could not connect to the hospital database."}

    try:
        cursor = conn.cursor()

        summary_sql = f"""
SELECT
    COUNT(*) AS Completed,
    SUM(CASE WHEN {actual_tat_expr} <= {expected_tat_expr} THEN 1 ELSE 0 END) AS WithinTAT,
    SUM(CASE WHEN {actual_tat_expr} > {expected_tat_expr} THEN 1 ELSE 0 END) AS OutsideTAT,
    AVG({actual_tat_expr}) AS AvgTAT
FROM trnInvStatus s
JOIN mstInvestigations inv ON s.TCODE = inv.INVCODE
JOIN trninvlabdet l ON s.BILLNO = l.BILLNO
{where_common}
"""
        cursor.execute(summary_sql)
        row = cursor.fetchone()
        completed = int(row[0] or 0)
        within = int(row[1] or 0)
        outside = int(row[2] or 0)
        avg_tat = float(row[3]) if row[3] is not None else None

        if completed == 0:
            return {
                "period_label": period_label,
                "completed": 0,
                "message": "No completed tests with both a real sample-collection and result-entry timestamp, and a defined TAT/SLA, were found for this period/location.",
            }

        compliance_pct = round((within / completed) * 100, 2) if completed else None

        test_sql = f"""
SELECT inv.INVNAME,
    COUNT(*) AS Completed,
    SUM(CASE WHEN {actual_tat_expr} > {expected_tat_expr} THEN 1 ELSE 0 END) AS OutsideCount
FROM trnInvStatus s
JOIN mstInvestigations inv ON s.TCODE = inv.INVCODE
JOIN trninvlabdet l ON s.BILLNO = l.BILLNO
{where_common}
GROUP BY inv.INVNAME
HAVING COUNT(*) >= 5
ORDER BY (SUM(CASE WHEN {actual_tat_expr} > {expected_tat_expr} THEN 1.0 ELSE 0 END) / COUNT(*)) DESC
"""
        cursor.execute(test_sql)
        test_rows = cursor.fetchall()[:5]
        top_delayed = [
            {"name": r[0], "outside_pct": round((r[2] / r[1]) * 100, 1) if r[1] else 0}
            for r in test_rows
        ]

        return {
            "period_label": period_label,
            "completed": completed,
            "within_tat": within,
            "outside_tat": outside,
            "compliance_pct": compliance_pct,
            "avg_tat_minutes": round(avg_tat, 1) if avg_tat is not None else None,
            "top_delayed_tests": top_delayed,
        }
    except Exception as e:
        return {"error": f"TAT dashboard query failed: {e}"}
    finally:
        conn.close()