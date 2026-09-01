import re

import pyodbc

from config import settings

# Only allow safe characters in a database name before it goes into the
# connection string. This is a defense-in-depth check: the caller (tools.py)
# should also validate db_name against the known institutions list, but this
# stops a malformed/malicious db_name from ever reaching the connection
# string even if that upstream check is ever skipped.
_SAFE_DB_NAME = re.compile(r"^[A-Za-z0-9_\-]+$")

# Drivers to try, newest first. The legacy "SQL Server" driver (DBNETLIB)
# is deprecated and can fail on connections that the modern ODBC Driver
# 17/18 handles fine — keeping it last as a fallback only.
_DRIVERS = [
    "ODBC Driver 18 for SQL Server",
    "ODBC Driver 17 for SQL Server",
    "SQL Server",
]


def _is_safe_db_name(db_name: str) -> bool:
    return bool(_SAFE_DB_NAME.match(db_name))


def get_hospital_connection(db_name: str = None):
    """
    Connect to a specific hospital's MSSQL database.

    db_name, when provided, MUST come from a trusted source (e.g. the
    validated license record's institution db_name) — never pass raw
    user input here directly.
    """
    database = db_name or settings.mssql_database

    if not _is_safe_db_name(database):
        print(f"Refusing to connect: unsafe database name '{database}'")
        return None

    last_error = None
    for driver in _DRIVERS:
        connection_string = (
            f"DRIVER={{{driver}}};"
            f"SERVER={settings.mssql_server};"
            f"DATABASE={database};"
            f"UID={settings.mssql_user};"
            f"PWD={settings.mssql_password};"
            "TrustServerCertificate=yes;"
            "Encrypt=no;"
        )
        try:
            return pyodbc.connect(connection_string, timeout=10)
        except Exception as e:
            last_error = e
            continue

    print(f"MSSQL Connection Error (all drivers failed): {last_error}")
    return None
