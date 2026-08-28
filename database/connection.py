import sqlite3
from typing import Optional

def get_hospital_connection(db_name: str = "hospital_demo"):
    """
    Connect to the hospital database.
    For testing we are using SQLite.
    Later we will switch to MySQL easily.
    """
    try:
        # For now we only have one test database
        connection = sqlite3.connect("hospital_demo.db")
        connection.row_factory = sqlite3.Row   # so we can get column names
        return connection
    except Exception as e:
        print(f"Database connection error: {e}")
        return None