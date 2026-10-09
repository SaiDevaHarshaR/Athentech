"""Per-institution column/metric profile for LIS clients."""
import json
from database.connection import get_hospital_connection
from database.license_db import get_conn

def _cols(cur, table: str) -> set:
    cur.execute(
        "SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = ?",
        (table,),
    )
    return {r[0] for r in cur.fetchall()}

def _pick(available: set, candidates: list) -> str | None:
    upper = {c.upper(): c for c in available}
    for name in candidates:
        if name.upper() in upper:
            return upper[name.upper()]
    return None

def scan_institution_profile(db_name, db_server=None, db_user=None, db_password=None) -> dict:
    conn = get_hospital_connection(db_name, db_server, db_user, db_password)
    if not conn:
        return {"error": "connect_failed"}
    try:
        cur = conn.cursor()
        coll_cols = _cols(cur, "trnMODEOFCOLLECTIONSDET")
        pat_cols = _cols(cur, "mstPatientRegistration")

        paid_c = _pick(coll_cols, ["PAIDAMOUNT", "PAIDAMT", "PAID"])
        total_c = _pick(coll_cols, ["TOTALAMOUNT", "TOTALCHARGES", "GRANDTOTAL", "AMOUNT"])
        due_c = _pick(coll_cols, ["DUEAMOUNT", "DUEAMT", "DUE"])
        date_c = _pick(coll_cols, ["DATEOFBILL", "BILLDATE"])
        reg_date = _pick(pat_cols, ["REGDATE", "REGISTRATIONDATE", "CREATEDATE", "ENTRYDATE"])
        reg_name = _pick(pat_cols, ["NAME", "PATIENTNAME", "PATIENT_NAME"])

        # last 7 days paid vs total
        paid_sum = total_sum = 0.0
        if paid_c and total_c and date_c:
            cur.execute(f"""
                SELECT SUM(ISNULL({paid_c},0)), SUM(ISNULL({total_c},0))
                FROM trnMODEOFCOLLECTIONSDET
                WHERE CAST({date_c} AS date) >= CAST(DATEADD(day,-7,GETDATE()) AS date)
            """)
            row = cur.fetchone() or (0, 0)
            paid_sum = float(row[0] or 0)
            total_sum = float(row[1] or 0)

        # Konnect-style if paid is meaningful; CentroMed-style if paid ~0 but total > 0
        if total_sum > 0 and paid_sum < total_sum * 0.1:
            collection_metric = "total"
        else:
            collection_metric = "paid"

        profile = {
            "collection_paid_col": paid_c or "PAIDAMOUNT",
            "collection_total_col": total_c or "TOTALAMOUNT",
            "collection_due_col": due_c or "DUEAMOUNT",
            "collection_date_col": date_c or "DATEOFBILL",
            "collection_metric": collection_metric,  # "paid" | "total"
            "patient_date_col": reg_date or "REGDATE",
            "patient_name_col": reg_name or "NAME",
            "paid_sum_7d": paid_sum,
            "total_sum_7d": total_sum,
        }
        return profile
    finally:
        conn.close()

def save_profile(institution_id: int, profile: dict):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = 'institution_schema_profile')
        CREATE TABLE institution_schema_profile (
            institution_id INT PRIMARY KEY,
            profile_json NVARCHAR(MAX) NOT NULL,
            updated_at DATETIME2 DEFAULT SYSUTCDATETIME()
        )
    """)
    # SQLite fallback if you still use sqlite licenses.db locally:
    # use CREATE TABLE IF NOT EXISTS without IF NOT EXISTS MSSQL style — adapt to your license_db.
    cur.execute(
        """
        MERGE institution_schema_profile AS t
        USING (SELECT ? AS institution_id) AS s ON t.institution_id = s.institution_id
        WHEN MATCHED THEN UPDATE SET profile_json = ?, updated_at = SYSUTCDATETIME()
        WHEN NOT MATCHED THEN INSERT (institution_id, profile_json) VALUES (?, ?);
        """,
        (institution_id, json.dumps(profile), institution_id, json.dumps(profile)),
    )
    conn.commit()
    conn.close()

def get_profile(institution_id: int) -> dict | None:
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT profile_json FROM institution_schema_profile WHERE institution_id = ?",
            (institution_id,),
        )
        row = cur.fetchone()
        if not row:
            return None
        return json.loads(row[0] if not hasattr(row, "keys") else row["profile_json"])
    except Exception:
        return None
    finally:
        conn.close()

def get_or_scan_profile(institution_id, db_name, db_server=None, db_user=None, db_password=None) -> dict:
    p = get_profile(institution_id)
    if p:
        return p
    p = scan_institution_profile(db_name, db_server, db_user, db_password)
    if "error" not in p and institution_id:
        save_profile(institution_id, p)
    return p