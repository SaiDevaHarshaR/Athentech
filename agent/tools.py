from langchain_core.tools import tool
import sqlite3
import pandas as pd
from auth.roles import Role, can_access_table

@tool
def run_sql_query(query: str, role: str = "viewer", db_name: str = "hospital_demo") -> str:
    """
    Execute a SELECT SQL query on the hospital database.
    Only SELECT queries are allowed.
    Access is restricted based on user role.
    """
    query = query.strip()

    # Only allow SELECT
    if not query.lower().startswith("select"):
        return "Error: Only SELECT queries are allowed."

    # Role-based table access check
    query_lower = query.lower()
    for table in ["patients", "admissions", "labs", "pharmacy", "wards",
                  "prescriptions", "doctors", "staff", "billing", "inventory"]:
        if table in query_lower:
            if not can_access_table(Role(role), table):
                return f"Access Denied: Your role ({role}) cannot access the '{table}' table."

    try:
        # Multi-hospital support
        db_file = f"{db_name}.db"
        conn = sqlite3.connect(db_file)
        conn.row_factory = sqlite3.Row

        df = pd.read_sql_query(query, conn)
        conn.close()

        if df.empty:
            return "No data found for this query."

        # Clean readable format
        lines = []
        for _, row in df.iterrows():
            item = [f"{col}: {row[col]}" for col in df.columns]
            lines.append("• " + " | ".join(item))

        return "\n".join(lines)

    except Exception as e:
        return f"Query failed: {str(e)}"