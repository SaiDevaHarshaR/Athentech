from langchain_core.tools import tool
import pandas as pd

from database.connection import get_hospital_connection
from auth.roles import Role
from auth.table_access import check_query_access, check_table_access
from auth.table_relationships import get_relationships_for_table


@tool
def describe_table(table_name: str, role: str = "viewer", db_name: str = None) -> str:
    """
    Look up the real column names and data types for a specific hospital
    database table. Call this BEFORE writing a SELECT query for a table
    you haven't queried yet in this conversation — do not guess column
    names, they will not match a demo/generic schema.
    """
    try:
        role_enum = Role(role)
    except ValueError:
        return f"Error: unknown role '{role}'."

    allowed, result = check_table_access(role_enum, table_name)
    if not allowed:
        return result
    clean_table_name = result

    conn = get_hospital_connection(db_name)
    if not conn:
        return "Error: Could not connect to the hospital database."

    try:
        query = (
            "SELECT COLUMN_NAME, DATA_TYPE "
            "FROM INFORMATION_SCHEMA.COLUMNS "
            "WHERE LOWER(TABLE_NAME) = ? "
            "ORDER BY ORDINAL_POSITION"
        )
        cursor = conn.cursor()
        cursor.execute(query, (clean_table_name,))
        rows = cursor.fetchall()
        conn.close()

        if not rows:
            return f"No columns found for table '{clean_table_name}' — check the table name."

        lines = [f"Columns for {clean_table_name}:"]
        for col_name, data_type in rows:
            lines.append(f"• {col_name} ({data_type})")

        # Reviewed join relationships, if any are known for this table —
        # included here (not a separate tool) so the agent gets join
        # guidance for free instead of costing another round-trip to ask
        # for it. See auth/table_relationships.py and
        # discover_table_relationships.py.
        relationships = get_relationships_for_table(clean_table_name)
        if relationships:
            lines.append("\nKnown joins:")
            for col, to_table, to_col in relationships:
                lines.append(f"• {clean_table_name}.{col} = {to_table}.{to_col}")

        return "\n".join(lines)

    except Exception as e:
        return f"Failed to describe table: {str(e)}"


@tool
def run_sql_query(query: str, role: str = "viewer", db_name: str = None) -> str:
    """
    Execute a SELECT SQL query on the real hospital MSSQL database.
    Only SELECT queries are allowed. Access is restricted based on user role.
    """
    query = query.strip()

    # Logged so wrong-table/wrong-column/wrong-date-format issues can
    # actually be diagnosed instead of guessed at — previously nothing
    # showed what SQL the agent was really generating.
    print(f"[run_sql_query] role={role} db={db_name}\nSQL: {query}")

    # Safety: Only SELECT
    if not query.lower().startswith("select"):
        return "Error: Only SELECT queries are allowed."

    # Real role-based table access check (default-deny for unmapped tables).
    # NOTE: `role` and `db_name` here are set by agent.py from the validated
    # license, not taken from the LLM's tool-call args — do not let this
    # function be called with caller-supplied role/db_name from anywhere else.
    try:
        role_enum = Role(role)
    except ValueError:
        return f"Error: unknown role '{role}'."

    allowed, reason = check_query_access(role_enum, query)
    if not allowed:
        return reason

    conn = get_hospital_connection(db_name)
    if not conn:
        return "Error: Could not connect to the hospital database."

    try:
        df = pd.read_sql(query, conn)
        conn.close()

        print(f"[run_sql_query] returned {len(df)} row(s)")

        if df.empty:
            return "No data found for this query."

        # Limit rows for safety (very important on real DB)
        df = df.head(50)

        # Clean readable format
        lines = []
        for _, row in df.iterrows():
            item = [f"{col}: {row[col]}" for col in df.columns]
            lines.append("• " + " | ".join(item))

        return "\n".join(lines)

    except Exception as e:
        print(f"[run_sql_query] FAILED: {e}")
        return f"Query failed: {str(e)}"