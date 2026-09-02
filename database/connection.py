import re

import pyodbc

from config import settings

# Only allow safe characters in a database name before it goes into the
# connection string. This is a defense-in-depth check: the caller (tools.py)
# should also validate db_name against the known institutions list, but this
# stops a malformed/malicious db_name from ever reaching the connection
# string even if that upstream check is ever skipped.
_SAFE_DB_NAME = re.compile(r"^[A-Za-z0-9_\-]+$")

# Server strings have more legitimate variety than db names — hostname,
# hostname,port / hostname\instance / IP,port are all real formats — but
# still must never contain characters that could break out of the
# connection string (;, ', ", =).
_SAFE_SERVER = re.compile(r"^[A-Za-z0-9_.\-\\,]+$")

# Same idea for a username: alphanumeric plus a few characters real DB
# logins commonly use, nothing that could inject extra connection
# string keys.
_SAFE_USER = re.compile(r"^[A-Za-z0-9_.\-@]+$")

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


def _is_safe_server(server: str) -> bool:
    return bool(_SAFE_SERVER.match(server))


def _is_safe_user(user: str) -> bool:
    return bool(_SAFE_USER.match(user))


def get_hospital_connection(
    db_name: str = None,
    db_server: str = None,
    db_user: str = None,
    db_password: str = None,
):
    """
    Connect to a specific hospital's MSSQL database.

    All four params, when provided, MUST come from a trusted source
    (the validated license record's institution row) — never pass raw
    user input here directly. Any that are None/empty fall back to the
    shared .env defaults (settings.mssql_*) — this is what makes
    per-institution db_server/db_user/db_password optional: an
    institution that doesn't need its own server/login just omits them
    and uses the same server as everyone else, same as before this
    feature existed.
    """
    database = db_name or settings.mssql_database
    server = db_server or settings.mssql_server
    user = db_user or settings.mssql_user
    # db_password is intentionally NOT regex-validated like the fields
    # above — real passwords legitimately contain punctuation (we've
    # already seen one with '#' in it), and this trusts the same source
    # (an admin-entered institution record) the other fields do.
    password = db_password or settings.mssql_password

    # Shows exactly what got resolved and whether each value came from
    # the per-institution override or the .env fallback — critical for
    # diagnosing exactly this kind of "wrong login for this database"
    # error without guessing which of the 4 values is actually wrong.
    print(
        f"[get_hospital_connection] database={database} "
        f"({'per-institution' if db_name else 'fallback .env'}), "
        f"server={server} ({'per-institution' if db_server else 'fallback .env'}), "
        f"user={user} ({'per-institution' if db_user else 'fallback .env'}), "
        f"password={'<per-institution, ' + str(len(db_password)) + ' chars>' if db_password else '<fallback .env>'}"
    )

    if not _is_safe_db_name(database):
        print(f"Refusing to connect: unsafe database name '{database}'")
        return None
    if not _is_safe_server(server):
        print(f"Refusing to connect: unsafe server value '{server}'")
        return None
    if not _is_safe_user(user):
        print(f"Refusing to connect: unsafe user value '{user}'")
        return None

    last_error = None
    for driver in _DRIVERS:
        connection_string = (
            f"DRIVER={{{driver}}};"
            f"SERVER={server};"
            f"DATABASE={database};"
            f"UID={user};"
            f"PWD={password};"
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