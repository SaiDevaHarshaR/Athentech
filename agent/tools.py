from langchain_core.tools import tool
from database.connection import get_hospital_connection
import pandas as pd

@tool
def run_sql_query(query: str, db_name: str = "hospital_demo") -> str:
    """Execute a SELECT SQL query on the hospital database and return results."""
    
    forbidden = ["insert", "update", "delete", "drop", "alter", "truncate", "create"]
    if any(word in query.lower() for word in forbidden):
        return "Error: Only SELECT queries are allowed."

    conn = get_hospital_connection(db_name)
    if not conn:
        return "Error: Could not connect to database."

    try:
        df = pd.read_sql_query(query, conn)
        conn.close()

        if df.empty:
            return "No data found for this query."

        return df.to_markdown(index=False)
    except Exception as e:
        return f"SQL Error: {str(e)}"