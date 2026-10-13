"""Adds the per-institution AI-key columns (AthenTech admin/license database only; never a client LIS database).
Self-contained: needs only get_conn() from license_db. Idempotent. READY tells the API whether AI-key storage works."""
from database.license_db import get_conn

READY = False
LAST_ERROR = ""

_COLS = [
    ("llm_provider", "NVARCHAR(50)"),
    ("llm_model", "NVARCHAR(150)"),
    ("llm_api_key", "NVARCHAR(1000)"),
    ("llm_base_url", "NVARCHAR(300)"),
    ("llm_key_status", "NVARCHAR(30)"),
    ("llm_key_checked_at", "NVARCHAR(50)"),
]


def _name(row):
    """Column name from an INFORMATION_SCHEMA row, for both the DictRow wrapper (by name) and a raw pyodbc Row (by index)."""
    try:
        return str(row["COLUMN_NAME"]).lower()
    except (KeyError, TypeError, IndexError):
        return str(row[0]).lower()


def ensure_llm_columns():
    global READY, LAST_ERROR
    conn = None
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = ?", ("institutions",))
        have = {_name(r) for r in cur.fetchall()}
        for col, typ in _COLS:
            if col.lower() not in have:
                cur.execute(f"ALTER TABLE institutions ADD {col} {typ}")
        conn.commit()
        cur.execute("SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = ?", ("institutions",))
        have = {_name(r) for r in cur.fetchall()}
        READY = all(c.lower() in have for c, _ in _COLS)
        LAST_ERROR = "" if READY else "columns still missing after migration"
    except Exception as e:
        READY, LAST_ERROR = False, f"{type(e).__name__}: {str(e)[:200]}"
    finally:
        try:
            if conn: conn.close()
        except Exception:
            pass
    if not READY:
        print(f"[startup] ERROR: AI-key storage NOT ready ({LAST_ERROR}). Clients keep using AthenTech's AI; saving a client key is blocked.", flush=True)
    return READY
