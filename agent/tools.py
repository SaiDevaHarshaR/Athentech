from langchain_core.tools import tool
from database.connection import get_hospital_connection
from auth.roles import Role
from auth.table_access import check_query_access, check_table_access


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

    # Safety: Only SELECT
    if not query.lower().startswith("select"):
        return "Error: Only SELECT queries are allowed."

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
        cursor = conn.cursor()
        cursor.execute(query)

        if not cursor.description:
            return "No data found for this query."

        columns = [col[0] for col in cursor.description]
        rows = cursor.fetchmany(50)  # safety limit

        if not rows:
            return "No data found for this query."

        lines = []
        for row in rows:
            item = [f"{columns[i]}: {row[i]}" for i in range(len(columns))]
            lines.append("• " + " | ".join(item))

        return "\n".join(lines)

    except Exception as e:
        return f"Query failed: {str(e)}"

    finally:
        try:
            conn.close()
        except Exception:
            pass