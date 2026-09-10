"""
TAT Compliance dashboard — real per-test SLA comparison, not a single
aggregate number. Uses mstInvestigations.TATTIME/TATTYPE (confirmed
real columns: TATTIME is a number-as-text, TATTYPE is 'Hours'/'Days')
as the expected TAT, compared against the actual computed TAT from
trnparamresult.BILLDATE-to-CREATEDATE (confirmed correct table/columns
for TAT elsewhere in this codebase — never trninvlabdet, it has no
CREATEDATE).

UNVERIFIED ASSUMPTION, flagged honestly: mstInvestigations.DEPARTMENTID
is joined here against mstsubdepartment.SubDepartmentID — this matches
the confirmed pattern for trninvlabdet.DEPTCODE elsewhere in this
system, but has NOT been independently confirmed for this specific
column. If department rollups look wrong, check this join first.
"""

from database.connection import get_hospital_connection


def get_tat_compliance_dashboard(
    department: str,
    period: str,
    db_name: str,
    db_server=None, db_user=None, db_password=None,
    specific_date: str = None,
    location_id: str = None,
) -> dict:
    """
    period: 'today' | 'yesterday' | 'this_week' | 'this_month' | 'day'
      (use period='day' with specific_date='YYYY-MM-DD' for one exact date)
    department: a department/sub-department name to filter by, or
    None/'' for all departments combined.
    location_id: a real LOC0X code (resolved one layer up via
    mstlocation, same pattern as get_lab_day_collection), or None for
    all locations combined.
    """
    if period == "day":
        import re
        if not specific_date or not re.match(r"^\d{4}-\d{2}-\d{2}$", specific_date):
            return {"error": f"period='day' requires a real specific_date (YYYY-MM-DD), got '{specific_date}'."}
        date_sql = f"BILLDATE >= '{specific_date}' AND BILLDATE < DATEADD(DAY, 1, CAST('{specific_date}' AS DATE))"
        period_label = specific_date
    elif period == "today":
        date_sql = "BILLDATE >= CAST(GETDATE() AS DATE) AND BILLDATE < DATEADD(DAY, 1, CAST(GETDATE() AS DATE))"
        period_label = "Today"
    elif period == "yesterday":
        date_sql = (
            "BILLDATE >= CAST(DATEADD(DAY, -1, GETDATE()) AS DATE) "
            "AND BILLDATE < CAST(GETDATE() AS DATE)"
        )
        period_label = "Yesterday"
    elif period == "this_week":
        date_sql = (
            "BILLDATE >= DATEADD(DAY, 1-DATEPART(WEEKDAY, GETDATE()), CAST(GETDATE() AS DATE)) "
            "AND BILLDATE < DATEADD(DAY, 1, CAST(GETDATE() AS DATE))"
        )
        period_label = "This Week"
    elif period == "this_month":
        date_sql = (
            "BILLDATE >= DATEADD(MONTH, DATEDIFF(MONTH, 0, GETDATE()), 0) "
            "AND BILLDATE < DATEADD(MONTH, DATEDIFF(MONTH, 0, GETDATE()) + 1, 0)"
        )
        period_label = "This Month"
    else:
        return {"error": f"Unsupported period '{period}'."}

    dept_sql = ""
    if department:
        dept_sql = (
            "AND inv.DEPARTMENTID IN ("
            "SELECT SubDepartmentID FROM mstsubdepartment "
            f"WHERE SubDeptName LIKE '%{department}%'"
            ") "
        )

    loc_sql = ""
    if location_id:
        loc_sql = f"AND p.LOCATIONID = '{location_id}' "

    # Expected TAT in minutes: Hours*60, Days*1440. NULL TATTIME/TATTYPE
    # (packages, or tests with no defined SLA) are excluded from
    # compliance — cannot classify within/outside without a real
    # threshold, and fabricating one would be a worse bug than omitting.
    expected_tat_expr = (
        "CASE "
        "WHEN inv.TATTYPE = 'Hours' THEN TRY_CAST(inv.TATTIME AS INT) * 60 "
        "WHEN inv.TATTYPE = 'Days' THEN TRY_CAST(inv.TATTIME AS INT) * 1440 "
        "ELSE NULL END"
    )
    actual_tat_expr = (
        "CAST(CASE WHEN DATEDIFF(MINUTE, p.BILLDATE, p.CREATEDATE) BETWEEN 0 AND 10080 "
        "THEN DATEDIFF(MINUTE, p.BILLDATE, p.CREATEDATE) END AS BIGINT)"
    )

    base_from = (
        "FROM trnparamresult p "
        "JOIN mstInvestigations inv ON p.INVCODE = inv.INVCODE "
        f"WHERE p.{date_sql} {dept_sql}{loc_sql}"
        f"AND inv.TATTIME IS NOT NULL AND inv.TATTYPE IS NOT NULL "
        f"AND {actual_tat_expr} IS NOT NULL"
    )

    conn = get_hospital_connection(db_name, db_server, db_user, db_password)
    if not conn:
        return {"error": "Could not connect to the hospital database."}

    try:
        cursor = conn.cursor()

        # Overall compliance
        summary_sql = f"""
SELECT
    COUNT(*) AS Completed,
    SUM(CASE WHEN {actual_tat_expr} <= {expected_tat_expr} THEN 1 ELSE 0 END) AS WithinTAT,
    SUM(CASE WHEN {actual_tat_expr} > {expected_tat_expr} THEN 1 ELSE 0 END) AS OutsideTAT,
    AVG({actual_tat_expr}) AS AvgTAT
{base_from}
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
                "department": department,
                "completed": 0,
                "message": "No completed tests with a defined TAT/SLA found for this period/department.",
            }

        compliance_pct = round((within / completed) * 100, 2) if completed else None

        # Worst department by compliance — build directly (can't reuse
        # base_from's shape, this needs an extra JOIN to mstsubdepartment)
        dept_sql_rollup = f"""
SELECT sd.SubDeptName,
    COUNT(*) AS Completed,
    SUM(CASE WHEN {actual_tat_expr} <= {expected_tat_expr} THEN 1 ELSE 0 END) AS WithinTAT
FROM trnparamresult p
JOIN mstInvestigations inv ON p.INVCODE = inv.INVCODE
JOIN mstsubdepartment sd ON inv.DEPARTMENTID = sd.SubDepartmentID
WHERE p.{date_sql} {dept_sql}{loc_sql}
AND inv.TATTIME IS NOT NULL AND inv.TATTYPE IS NOT NULL
AND {actual_tat_expr} IS NOT NULL
GROUP BY sd.SubDeptName
HAVING COUNT(*) >= 5
ORDER BY (SUM(CASE WHEN {actual_tat_expr} <= {expected_tat_expr} THEN 1.0 ELSE 0 END) / COUNT(*)) ASC
"""
        cursor.execute(dept_sql_rollup)
        dept_rows = cursor.fetchall()
        worst_dept = None
        if dept_rows:
            name, dept_completed, dept_within = dept_rows[0]
            dept_compliance = round((dept_within / dept_completed) * 100, 1) if dept_completed else 0
            worst_dept = {"name": name, "compliance_pct": dept_compliance, "completed": dept_completed}

        # Top delayed tests by % outside TAT
        test_sql = f"""
SELECT inv.INVNAME,
    COUNT(*) AS Completed,
    SUM(CASE WHEN {actual_tat_expr} > {expected_tat_expr} THEN 1 ELSE 0 END) AS OutsideCount
FROM trnparamresult p
JOIN mstInvestigations inv ON p.INVCODE = inv.INVCODE
WHERE p.{date_sql} {dept_sql}{loc_sql}
AND inv.TATTIME IS NOT NULL AND inv.TATTYPE IS NOT NULL
AND {actual_tat_expr} IS NOT NULL
GROUP BY inv.INVNAME
HAVING COUNT(*) >= 5
ORDER BY (SUM(CASE WHEN {actual_tat_expr} > {expected_tat_expr} THEN 1.0 ELSE 0 END) / COUNT(*)) DESC
"""
        cursor.execute(test_sql)
        test_rows = cursor.fetchall()[:5]
        top_delayed = [
            {
                "name": r[0],
                "outside_pct": round((r[2] / r[1]) * 100, 1) if r[1] else 0,
            }
            for r in test_rows
        ]

        return {
            "period_label": period_label,
            "department": department,
            "completed": completed,
            "within_tat": within,
            "outside_tat": outside,
            "compliance_pct": compliance_pct,
            "avg_tat_minutes": round(avg_tat, 1) if avg_tat is not None else None,
            "worst_dept": worst_dept,
            "top_delayed_tests": top_delayed,
        }
    except Exception as e:
        return {"error": f"TAT dashboard query failed: {e}"}
    finally:
        conn.close()