"""
Audit log — migrated from a flat JSON-lines file (audit/audit.log) to
the same Turso database used for institutions/licenses/admins. Real
reasons for the migration, not just consistency:
  - Flat file had no real unique ID (only insertion order) — the admin
    panel wants a real sequential ID per event.
  - Flat file couldn't be filtered/date-ranged efficiently — every
    request re-read and re-parsed the whole file.
  - Never captured the actual answer or token count — both needed now
    for the audit detail expansion.

Same public function names (audit, read_audit_log) so call sites don't
need to change beyond passing the two new optional fields (answer,
tokens_used).
"""

from datetime import datetime

from database.license_db import get_conn


def init_audit_table():
    """Call once alongside init_license_db() at startup."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS audit_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT NOT NULL,
        event TEXT NOT NULL,
        role TEXT,
        code TEXT,
        question TEXT,
        answer TEXT,
        tokens_used INTEGER,
        meta TEXT
    )
    """)
    conn.commit()
    conn.close()


def audit(event: str, role: str = None, code: str = None, question: str = None,
          answer: str = None, tokens_used: int = None, meta: dict = None):
    """
    Same signature as before, plus two new optional fields: answer and
    tokens_used. Existing call sites that don't pass these still work
    unchanged — they'll just show as empty in the audit detail view.

    Question/answer are trimmed generously (not to 120 chars like the
    old file-based version) since the new detail-expansion view is
    meant to show real content, not just a title-length preview — but
    still capped to keep any one row from being unreasonably large.
    """
    import json

    safe_question = (question or "")[:2000]
    safe_answer = (answer or "")[:4000]

    conn = get_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO audit_logs (ts, event, role, code, question, answer, tokens_used, meta) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                datetime.utcnow().isoformat() + "Z",
                event,
                role,
                code,
                safe_question,
                safe_answer,
                tokens_used,
                json.dumps(meta or {}),
            )
        )
        conn.commit()
    except Exception as e:
        # Never let a logging failure break the actual request it's
        # trying to log — same principle as the old file-based version
        # silently appending rather than raising.
        print(f"[audit] Failed to write audit log (non-fatal): {e}")
    finally:
        conn.close()


def read_audit_log(limit: int = 500, search: str = None, event_type: str = None,
                    date_from: str = None, date_to: str = None) -> list:
    """
    Returns the most recent `limit` audit events, newest first, with
    real filtering pushed down to the query instead of the old
    approach of loading everything and filtering in Python/JS.

    date_from / date_to: ISO date strings (YYYY-MM-DD), inclusive.
    """
    import json

    conn = get_conn()
    try:
        cur = conn.cursor()

        where_clauses = []
        params = []

        if search:
            where_clauses.append(
                "(question LIKE ? OR answer LIKE ? OR code LIKE ? OR event LIKE ?)"
            )
            like_term = f"%{search}%"
            params.extend([like_term, like_term, like_term, like_term])

        if event_type and event_type != "all":
            where_clauses.append("event = ?")
            params.append(event_type)

        if date_from:
            where_clauses.append("ts >= ?")
            params.append(date_from)

        if date_to:
            where_clauses.append("ts <= ?")
            params.append(date_to + "T23:59:59Z")

        where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

        cur.execute(
            f"SELECT id, ts, event, role, code, question, answer, tokens_used, meta "
            f"FROM audit_logs {where_sql} ORDER BY id DESC LIMIT ?",
            (*params, limit)
        )
        rows = cur.fetchall()

        records = []
        for row in rows:
            record = dict(row.items())
            try:
                record["meta"] = json.loads(record["meta"] or "{}")
            except (json.JSONDecodeError, TypeError):
                record["meta"] = {}
            records.append(record)

        return records
    finally:
        conn.close()