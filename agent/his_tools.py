"""
HIS-specific variants of describe_table/run_sql_query. Same SQL safety
guardrails as the LIS tools (SELECT-only, banned keywords, schema
validation against real MSSQL columns) — but WITHOUT the LIS-oriented
REAL_TABLE_TO_CATEGORY access-control gate, since none of the HIS
tblXxx tables are mapped there and denying every one of them by
default made every HIS ad-hoc question fail with a false "no access"
error.

Deliberate, temporary tradeoff: any authenticated premium HIS user can
query any HIS table right now, regardless of role. Revisit once a real
HIS role/category map exists (mirroring auth/table_access.py's
REAL_TABLE_TO_CATEGORY, built for tblXxx-style tables instead).
"""

import re
from langchain_core.tools import tool
from database.connection import get_hospital_connection
from agent.tools import get_request_schema_cache


@tool
def his_describe_table(table_name: str, role: str = "viewer", db_name: str = None,
                        db_server: str = None, db_user: str = None, db_password: str = None) -> str:
    """
    HIS version of describe_table — look up real column names/types for
    a Hospital (HIS) database table. No category-based access
    restriction (see module docstring). Call this before writing a
    SELECT query for any tblXxx table you haven't queried yet this
    conversation.
    """
    clean_table_name = table_name.strip().strip("[]").split(".")[-1]

    conn = get_hospital_connection(db_name, db_server, db_user, db_password)
    if not conn:
        return "Error: Could not connect to the hospital database."

    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COLUMN_NAME, DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS "
            "WHERE LOWER(TABLE_NAME) = ? ORDER BY ORDINAL_POSITION",
            (clean_table_name.lower(),),
        )
        rows = cursor.fetchall()
        if not rows:
            return f"No columns found for table '{clean_table_name}' — check the table name."

        get_request_schema_cache()[clean_table_name.lower()] = {c.lower() for c, _ in rows}

        lines = [f"Columns for {clean_table_name}:"]
        for col_name, data_type in rows:
            lines.append(f"• {col_name} ({data_type})")
        return "\n".join(lines)
    except Exception as e:
        return f"Failed to describe table: {e}"
    finally:
        try:
            conn.close()
        except Exception:
            pass


@tool
def his_run_sql_query(query: str, role: str = "viewer", db_name: str = None,
                       db_server: str = None, db_user: str = None, db_password: str = None) -> str:
    """
    HIS version of run_sql_query — execute a SELECT query on the
    hospital HIS database. Same SQL safety rules as the LIS tool
    (SELECT-only, no write keywords), but no category-based access
    restriction (see module docstring).
    """
    query = query.strip()
    print(f"[his_run_sql_query] role={role} db={db_name}\nSQL: {query}")

    if not query.lower().startswith("select"):
        return "Error: Only SELECT queries are allowed."

    banned = [" insert ", " update ", " delete ", " drop ", " alter ", " truncate ", " exec ", " merge ", " xp_"]
    qpad = f" {query.lower()} "
    if any(b in qpad for b in banned):
        return "Error: Only read-only SELECT is allowed."

    conn = get_hospital_connection(db_name, db_server, db_user, db_password)
    if not conn:
        return "Error: Could not connect to the hospital database."

    try:
        cursor = conn.cursor()
        cursor.execute(query)

        if not cursor.description:
            return "No data found for this query."

        columns = [c[0] for c in cursor.description]
        rows = cursor.fetchmany(50)
        print(f"[his_run_sql_query] returned {len(rows)} row(s)")

        if not rows:
            return "No data found for this query."

        lines = []
        for row in rows:
            item = [f"{columns[i]}: {row[i]}" for i in range(len(columns))]
            lines.append("• " + " | ".join(item))
        return "\n".join(lines)
    except Exception as e:
        print(f"[his_run_sql_query] FAILED: {e}")
        return f"Query failed: {e}"
    finally:
        try:
            conn.close()
        except Exception:
            pass