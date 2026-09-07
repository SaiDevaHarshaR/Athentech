from langchain_core.tools import tool

from database.connection import get_hospital_connection
from auth.roles import Role
from auth.table_access import check_query_access, check_table_access
from auth.table_relationships import get_relationships_for_table


@tool
def describe_table(
    table_name: str,
    role: str = "viewer",
    db_name: str = None,
    db_server: str = None,
    db_user: str = None,
    db_password: str = None,
) -> str:
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

    conn = get_hospital_connection(db_name, db_server, db_user, db_password)
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

        if not rows:
            return f"No columns found for table '{clean_table_name}' — check the table name."

        lines = [f"Columns for {clean_table_name}:"]
        for col_name, data_type in rows:
            lines.append(f"• {col_name} ({data_type})")

        relationships = get_relationships_for_table(clean_table_name)
        if relationships:
            lines.append("\nKnown joins:")
            for col, to_table, to_col in relationships:
                lines.append(f"• {clean_table_name}.{col} = {to_table}.{to_col}")

        return "\n".join(lines)

    except Exception as e:
        return f"Failed to describe table: {str(e)}"
    finally:
        try:
            conn.close()
        except Exception:
            pass


@tool
def run_sql_query(
    query: str,
    role: str = "viewer",
    db_name: str = None,
    db_server: str = None,
    db_user: str = None,
    db_password: str = None,
) -> str:
    """
    Execute a SELECT SQL query on the real hospital MSSQL database.
    Only SELECT queries are allowed. Access is restricted based on user role.
    """
    query = query.strip()

    print(f"[run_sql_query] role={role} db={db_name}\nSQL: {query}")

    if not query.lower().startswith("select"):
        return "Error: Only SELECT queries are allowed."

    banned = [" insert ", " update ", " delete ", " drop ", " alter ", " truncate ", " exec ", " merge ", " xp_"]
    qpad = f" {query.lower()} "
    if any(b in qpad for b in banned):
        return "Error: Only read-only SELECT is allowed."

    try:
        role_enum = Role(role)
    except ValueError:
        return f"Error: unknown role '{role}'."

    allowed, reason = check_query_access(role_enum, query)
    if not allowed:
        return reason

    conn = get_hospital_connection(db_name, db_server, db_user, db_password)
    if not conn:
        return "Error: Could not connect to the hospital database."

    try:
        cursor = conn.cursor()
        cursor.execute(query)

        if not cursor.description:
            print("[run_sql_query] returned 0 row(s)")
            return "No data found for this query."

        columns = [c[0] for c in cursor.description]
        rows = cursor.fetchmany(50)

        print(f"[run_sql_query] returned {len(rows)} row(s)")

        if not rows:
            return "No data found for this query."

        lines = []
        for row in rows:
            item = [f"{columns[i]}: {row[i]}" for i in range(len(columns))]
            lines.append("• " + " | ".join(item))

        return "\n".join(lines)

    except Exception as e:
        print(f"[run_sql_query] FAILED: {e}")
        return f"Query failed: {str(e)}"
    finally:
        try:
            conn.close()
        except Exception:
            pass


@tool
def get_verified_day_collection(
    location_keyword: str,
    date_from: str,
    date_to: str,
    role: str = "viewer",
    db_name: str = None,
    db_server: str = None,
    db_user: str = None,
    db_password: str = None,
) -> str:
    """
    Day collection by location and date range, using a FIXED, hand-
    verified query — not one you write yourself. Use this INSTEAD of
    run_sql_query whenever the question is about collection/revenue for
    a specific location and date range — it's guaranteed correct where
    a freshly-written query has repeatedly guessed wrong column/value
    names for this exact pattern.

    date_from and date_to MUST be 'YYYY-MM-DD' (convert "today"/
    "yesterday"/"this month" to real dates yourself before calling).
    location_keyword: the distinctive part of the location name from
    the question (e.g. "Kompally") — partial match, don't need the
    exact full stored name.
    """
    from reports.curated_queries import get_day_collection

    if role not in ("admin", "doctor", "reception"):
        # Same billing-category gate as the rest of the system —
        # this tool bypasses check_query_access's SQL text parsing
        # (there's no SQL text to parse, it's fixed), so the role
        # check has to happen explicitly here instead.
        return "Error: your role does not have access to billing/collection data."

    result = get_day_collection(location_keyword, date_from, date_to, db_name, db_server, db_user, db_password)

    if "error" in result:
        return f"Error: {result['error']}"

    if result.get("ambiguous"):
        candidates = ", ".join(result["candidates"])
        return (
            f"Multiple locations match '{location_keyword}': {candidates}. "
            "Ask the user which one they mean rather than guessing."
        )

    if result.get("no_data"):
        return (
            f"No collection records found for {result['location']} between "
            f"{result['date_from']} and {result['date_to']}. This is a real "
            f"query result (not a guessed wrong column), so this is either "
            f"genuinely no activity in that window, or a data lag — say so "
            f"plainly, don't invent a reason."
        )

    lines = [f"Location: {result['location']} | {result['date_from']} to {result['date_to']}"]
    lines.append(f"Total: {result['total']}")
    for b in result["breakdown"]:
        lines.append(f"  {b['mode']}: {b['amount']}")
    return "\n".join(lines)