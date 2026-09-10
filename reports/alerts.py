"""
Alerts — zero-collection and TAT-compliance only. Stock/inventory
alerts are NOT included — no confirmed inventory table exists yet.
"""

from database.connection import get_hospital_connection


def check_zero_collection_locations(date_str: str, db_name: str, db_server=None, db_user=None, db_password=None) -> dict:
    """
    Real locations (mstlocation, ACTIVE=1) with ZERO rows in
    trnmodeofcollectionsdet for the given date. date_str: 'YYYY-MM-DD'.
    """
    conn = get_hospital_connection(db_name, db_server, db_user, db_password)
    if not conn:
        return {"error": "Could not connect to the hospital database."}
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT loc.LOCATIONID, loc.LOCATIONNAME
            FROM mstlocation loc
            WHERE loc.ACTIVE = 1
            AND loc.LOCATIONNAME NOT IN ('eCommerce', 'Stores')
            AND NOT EXISTS (
                SELECT 1 FROM trnmodeofcollectionsdet m
                WHERE m.LOCATIONID = loc.LOCATIONID
                AND m.DATEOFBILL >= ? AND m.DATEOFBILL < DATEADD(DAY, 1, CAST(? AS DATE))
            )
            """,
            (date_str, date_str),
        )
        rows = cursor.fetchall()
        return {"date": date_str, "zero_collection_locations": [{"id": r[0], "name": r[1]} for r in rows]}
    except Exception as e:
        return {"error": f"Zero-collection check failed: {e}"}
    finally:
        conn.close()


def check_tat_compliance_alert(threshold_pct: float, period: str, db_name: str, db_server=None, db_user=None, db_password=None, specific_date: str = None, location_id: str = None) -> dict:
    """
    Flags if TAT compliance falls below threshold_pct for the period.
    Reuses the confirmed-working get_tat_compliance_dashboard directly
    — does not reimplement its logic.
    """
    from reports.tat_dashboard import get_tat_compliance_dashboard
    result = get_tat_compliance_dashboard(period, db_name, db_server, db_user, db_password, specific_date, location_id)
    if "error" in result:
        return result
    if result.get("completed") == 0:
        return {"alert": False, "reason": result.get("message")}
    below = result["compliance_pct"] < threshold_pct
    return {
        "alert": below,
        "compliance_pct": result["compliance_pct"],
        "threshold_pct": threshold_pct,
        "period_label": result["period_label"],
    }