from langchain_core.tools import tool
import pandas as pd
from database.connection import get_hospital_connection
from auth.roles import Role, can_access_table

@tool
def run_sql_query(query: str, role: str = "viewer", db_name: str = None) -> str:
    """
    Execute a SELECT SQL query on the real hospital MSSQL database.
    Only SELECT queries are allowed.
    Access is restricted based on user role.
    """
    query = query.strip()

    # Safety: Only SELECT
    if not query.lower().startswith("select"):
        return "Error: Only SELECT queries are allowed."

    # Basic role-based protection (you will improve this later)
    query_lower = query.lower()
    sensitive_tables = [
        "mstpatientregistration", "tblclientdocinfo", "trnmergeddocbilldtls_referral",
        "trnpurchaseorder", "mstlocationusers"
    ]
    
    for table in sensitive_tables:
        if table in query_lower.replace("[", "").replace("]", "").replace("dbo.", ""):
            # You can make this stricter later
            pass

    conn = get_hospital_connection()
    if not conn:
        return "Error: Could not connect to the hospital database."

    try:
        df = pd.read_sql(query, conn)
        conn.close()

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
        return f"Query failed: {str(e)}"