from langchain_core.tools import tool
from database.connection import get_hospital_connection
from auth.roles import Role, get_allowed_tables
import pandas as pd
import re

@tool
def run_sql_query(query: str, db_name: str = "hospital_demo", role: str = "viewer") -> str:
    """
    Execute a SELECT SQL query on the hospital database.
    Access is restricted based on the user's role.
    """
    # Safety check
    forbidden = ["insert", "update", "delete", "drop", "alter", "truncate", "create", "grant"]
    if any(word in query.lower() for word in forbidden):
        return "Error: Only SELECT queries are allowed."

    # Extract table names
    tables_in_query = set()
    matches = re.findall(r'(?:FROM|JOIN)\s+(\w+)', query, re.IGNORECASE)
    tables_in_query.update([t.lower() for t in matches])

    try:
        user_role = Role(role)
    except ValueError:
        user_role = Role.VIEWER

    allowed = get_allowed_tables(user_role)

    for table in tables_in_query:
        if table not in allowed:
            return f"Access Denied: Role '{role}' cannot access table '{table}'. Allowed tables: {', '.join(sorted(allowed))}"

    conn = get_hospital_connection(db_name)
    if not conn:
        return "Error: Could not connect to database."

    try:
        df = pd.read_sql_query(query, conn)
        conn.close()

        if df.empty:
            return "No data found for this query."
        result_lines = []
        for _, row in df.iterrows():
            row_str = " | ".join([f"{col}: {val}" for col, val in row.items()])
            result_lines.append(f"• {row_str}")
        
        return "\n".join(result_lines)

        return df.to_markdown(index=False)
    except Exception as e:
        return f"SQL Error: {str(e)}"