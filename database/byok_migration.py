"""Adds the per-institution AI-key columns (AthenTech admin/license database only; never a client LIS database).
Self-contained: needs only get_conn() from license_db. Idempotent. READY tells the API whether AI-key storage works."""
from database.license_db import get_conn

READY = False
SLOTS_READY = False
LAST_ERROR = ""

_COLS = [
    ("llm_provider", "NVARCHAR(50)"),
    ("llm_model", "NVARCHAR(150)"),
    ("llm_api_key", "NVARCHAR(1000)"),
    ("llm_base_url", "NVARCHAR(300)"),
    ("llm_key_status", "NVARCHAR(30)"),
    ("llm_key_checked_at", "NVARCHAR(50)"),
    ("allow_athentech_fallback", "BIT NOT NULL DEFAULT (0)"),
]


def _name(row):
    """Column name from an INFORMATION_SCHEMA row, for both the DictRow wrapper (by name) and a raw pyodbc Row (by index)."""
    try:
        return str(row["COLUMN_NAME"]).lower()
    except (KeyError, TypeError, IndexError):
        return str(row[0]).lower()


def ensure_llm_columns():
    global READY, SLOTS_READY, LAST_ERROR
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
        if READY:
            cur.execute("SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = ?", ("institution_ai_slots",))
            if cur.fetchone() is None:
                cur.execute("""CREATE TABLE institution_ai_slots (
                    id INT IDENTITY(1,1) PRIMARY KEY,
                    institution_id INT NOT NULL,
                    position INT NOT NULL,
                    enabled BIT NOT NULL DEFAULT (1),
                    provider NVARCHAR(50) NULL,
                    model NVARCHAR(150) NULL,
                    api_key NVARCHAR(2048) NULL,
                    base_url NVARCHAR(350) NULL,
                    key_status NVARCHAR(30) NULL,
                    checked_at NVARCHAR(50) NULL,
                    CONSTRAINT UQ_institution_ai_slots_position UNIQUE (institution_id, position)
                )""")
                conn.commit()
            cur.execute("SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = ?", ("institution_ai_slots",))
            SLOTS_READY = cur.fetchone() is not None
        READY = READY and SLOTS_READY
        LAST_ERROR = "" if READY else "AI configuration table/columns missing after migration"
    except Exception as e:
        READY, SLOTS_READY, LAST_ERROR = False, False, f"{type(e).__name__}: {str(e)[:200]}"
    finally:
        try:
            if conn: conn.close()
        except Exception:
            pass
    if not READY:
        print(f"[startup] ERROR: AI-key storage NOT ready ({LAST_ERROR}). Client AI is blocked until this migration succeeds; normal AthenTech mode remains available.", flush=True)
    return READY
