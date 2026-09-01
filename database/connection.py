import pyodbc
from config import settings

def get_hospital_connection(db_name: str = None):
    try:
        connection_string = (
            "DRIVER={SQL Server};"
            f"SERVER={settings.mssql_server};"
            f"DATABASE={settings.mssql_database};"
            f"UID={settings.mssql_user};"
            f"PWD={settings.mssql_password};"
        )

        conn = pyodbc.connect(connection_string, timeout=10)
        return conn

    except Exception as e:
        print(f"MSSQL Connection Error: {e}")
        return None