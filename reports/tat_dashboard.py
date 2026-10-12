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
    department: str = None,
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
    dept_sql = ""
    if department:
        from agent.schema_ctx import get_profile, radiology_dept_sql
        _c = get_hospital_connection(db_name, db_server, db_user, db_password)
        if _c:
            try:
                _d = radiology_dept_sql(get_profile(_c, db_name, db_server), department, "dd.DEPTCODE")
                dept_sql = (f"AND EXISTS (SELECT 1 FROM trninvlabdet dd WHERE dd.BILLNO = s.BILLNO "
                            f"AND dd.TCODE = s.TCODE AND {_d}) ")
            finally:
                _c.close()
    if location_id:
        loc_sql = f"AND l.LOCATIONID = '{location_id}' "

    # Light query: ONE pass over trnInvStatus grouped per test; location is an
    # EXISTS (never a BILLNO join, which multiplied rows per test on a bill).
    # Rolled up in Python. Expected TAT is computed once per test in the group.
    loc_sql = ""
    if location_id:
        loc_sql = ("AND EXISTS (SELECT 1 FROM trninvlabdet l WHERE l.BILLNO = s.BILLNO "
                   f"AND l.LOCATIONID = '{location_id}') ")
    sql = f"""
SELECT inv.INVNAME, inv.TATTYPE, inv.TATTIME,
       COUNT(*) AS N,
       SUM(CASE WHEN DATEDIFF(MINUTE, s.SAMPLECOLLECTEDDATE, s.RESULTENTRYDATE)
                <= CASE WHEN inv.TATTYPE = 'Hours' THEN TRY_CAST(inv.TATTIME AS INT) * 60
                        ELSE TRY_CAST(inv.TATTIME AS INT) * 1440 END THEN 1 ELSE 0 END) AS Within,
       SUM(CAST(DATEDIFF(MINUTE, s.SAMPLECOLLECTEDDATE, s.RESULTENTRYDATE) AS BIGINT)) AS SumMin
FROM trnInvStatus s
JOIN mstInvestigations inv ON s.TCODE = inv.INVCODE
WHERE {date_sql} {loc_sql} {dept_sql}
  AND s.SAMPLECOLLECTEDDATE IS NOT NULL AND s.RESULTENTRYDATE IS NOT NULL
  AND s.RESULTENTRYDATE >= s.SAMPLECOLLECTEDDATE
  AND s.RESULTENTRYDATE < DATEADD(DAY, 7, s.SAMPLECOLLECTEDDATE)
  AND inv.TATTYPE IN ('Hours','Days') AND TRY_CAST(inv.TATTIME AS INT) > 0
GROUP BY inv.INVNAME, inv.TATTYPE, inv.TATTIME
"""
    conn = get_hospital_connection(db_name, db_server, db_user, db_password)
    if not conn:
        return {"error": "Could not connect to the hospital database."}
    try:
        cursor = conn.cursor()
        try:
            cursor.timeout = 60
        except Exception:
            pass
        cursor.execute(sql)
        rows = cursor.fetchall()
        completed = sum(int(r[3] or 0) for r in rows)
        within = sum(int(r[4] or 0) for r in rows)
        outside = completed - within
        if completed == 0:
            return {
                "period_label": period_label,
                "completed": 0,
                "message": "No completed tests with both a real sample-collection and result-entry timestamp, and a defined TAT/SLA, were found for this period/location.",
            }
        avg_tat = sum(float(r[5] or 0) for r in rows) / completed
        compliance_pct = round((within / completed) * 100, 2)
        per_test = [(r[0], int(r[3]), int(r[3]) - int(r[4] or 0)) for r in rows if int(r[3]) >= 5]
        per_test.sort(key=lambda x: x[2] / x[1], reverse=True)
        top_delayed = [{"name": n, "outside_pct": round(o / c * 100, 1)} for n, c, o in per_test[:5]]
        return {
            "period_label": period_label,
            "completed": completed,
            "within_tat": within,
            "outside_tat": outside,
            "compliance_pct": compliance_pct,
            "avg_tat_minutes": round(avg_tat, 1),
            "top_delayed_tests": top_delayed,
        }
    except Exception as e:
        return {"error": f"TAT dashboard query failed: {e}"}
    finally:
        conn.close()