"""
Admin/license database — MSSQL-backed. Migrated from Turso (SQLite),
which was used during testing since it was genuinely free forever
with no pause-on-inactivity. Now that AthenTech has real MSSQL
licenses, this uses the same database technology as the rest of the
stack — one thing to monitor/back up instead of a separate external
dependency.

Connection details come from environment variables so moving from
test to production is purely an .env change, no code change:
    ADMIN_DB_SERVER   (e.g. "myserver.database.windows.net" or "192.168.0.163")
    ADMIN_DB_PORT      (e.g. "1433")
    ADMIN_DB_NAME      (e.g. "SahasraAdmin")
    ADMIN_DB_USER
    ADMIN_DB_PASSWORD

Note: this is genuinely untested against a live MSSQL server — I
cannot run pyodbc against a real SQL Server instance from this
sandbox. Real verification is needed on the actual server, the same
way every other piece this session was tested there.
"""

import os
from datetime import datetime

import pyodbc
from dotenv import load_dotenv

load_dotenv()

_ADMIN_DB_SERVER = os.environ.get("ADMIN_DB_SERVER", "")
_ADMIN_DB_PORT = os.environ.get("ADMIN_DB_PORT", "1433")
_ADMIN_DB_NAME = os.environ.get("ADMIN_DB_NAME", "")
_ADMIN_DB_USER = os.environ.get("ADMIN_DB_USER", "")
_ADMIN_DB_PASSWORD = os.environ.get("ADMIN_DB_PASSWORD", "")


# ---------------------------------------------------------------------------
# Dict-style row access — every existing caller across the codebase does
# row["column_name"], not row.column_name or positional indexing. pyodbc's
# native Row object supports attribute access but not dict-style bracket
# access, so this wrapper bridges that gap without touching every call site.
# ---------------------------------------------------------------------------
class DictRow:
    def __init__(self, row, columns):
        self._data = dict(zip(columns, row))

    def __getitem__(self, key):
        return self._data[key]

    def get(self, key, default=None):
        return self._data.get(key, default)

    def items(self):
        return self._data.items()

    def keys(self):
        return self._data.keys()


class DictCursor:
    def __init__(self, real_cursor):
        self._cursor = real_cursor

    def execute(self, sql, params=None):
        if params:
            self._cursor.execute(sql, params)
        else:
            self._cursor.execute(sql)
        return self

    def fetchone(self):
        row = self._cursor.fetchone()
        if row is None:
            return None
        columns = [d[0] for d in self._cursor.description]
        return DictRow(row, columns)

    def fetchall(self):
        rows = self._cursor.fetchall()
        if not rows:
            return []
        columns = [d[0] for d in self._cursor.description]
        return [DictRow(r, columns) for r in rows]

    @property
    def rowcount(self):
        return self._cursor.rowcount

    @property
    def description(self):
        return self._cursor.description

    @property
    def lastrowid(self):
        # pyodbc has no native lastrowid (that's a SQLite-ism) — MSSQL's
        # real equivalent is SCOPE_IDENTITY(), queried immediately after
        # an INSERT on an IDENTITY column, in the same connection/scope.
        self._cursor.execute("SELECT SCOPE_IDENTITY() AS id")
        row = self._cursor.fetchone()
        return int(row[0]) if row and row[0] is not None else None


class DictConn:
    def __init__(self, real_conn):
        self._conn = real_conn

    def cursor(self):
        return DictCursor(self._conn.cursor())

    def execute(self, sql, params=None):
        # Convenience for the common "conn.execute(...).fetchall()" pattern
        # used throughout the codebase (mirrors sqlite3.Connection's
        # execute shortcut, which pyodbc's raw connection doesn't have).
        cur = self.cursor()
        cur.execute(sql, params)
        return cur

    def commit(self):
        self._conn.commit()

    def close(self):
        self._conn.close()


def get_conn() -> DictConn:
    conn_str = (
        f"DRIVER={{ODBC Driver 18 for SQL Server}};"
        f"SERVER={_ADMIN_DB_SERVER},{_ADMIN_DB_PORT};"
        f"DATABASE={_ADMIN_DB_NAME};"
        f"UID={_ADMIN_DB_USER};"
        f"PWD={_ADMIN_DB_PASSWORD};"
        f"TrustServerCertificate=yes;"
    )
    raw_conn = pyodbc.connect(conn_str, timeout=10)
    return DictConn(raw_conn)


def _table_exists(cur, table_name: str) -> bool:
    cur.execute(
        "SELECT 1 FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = ?",
        (table_name,)
    )
    return cur.fetchone() is not None


def _column_exists(cur, table_name: str, column_name: str) -> bool:
    cur.execute(
        "SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = ? AND COLUMN_NAME = ?",
        (table_name, column_name)
    )
    return cur.fetchone() is not None


def init_license_db():
    """
    Creates every table if it doesn't already exist, and adds any
    columns that were introduced after the original schema (email,
    two_factor_method, totp_secret, institution_type) — same
    "ALTER TABLE if missing" safety net as the SQLite version had, so
    this is safe to call on every startup without wiping real data.
    """
    conn = get_conn()
    cur = conn.cursor()

    if not _table_exists(cur, "institutions"):
        cur.execute("""
        CREATE TABLE institutions (
            id INT IDENTITY(1,1) PRIMARY KEY,
            name NVARCHAR(255) NOT NULL,
            code NVARCHAR(50) NOT NULL UNIQUE,
            client_prefix NVARCHAR(50) NOT NULL,
            db_name NVARCHAR(255),
            db_server NVARCHAR(255),
            db_user NVARCHAR(255),
            db_password NVARCHAR(500),
            type NVARCHAR(50) DEFAULT 'Diagnostic',
            city NVARCHAR(100),
            status NVARCHAR(50) DEFAULT 'Active',
            created_at NVARCHAR(50)
        )
        """)

    if not _table_exists(cur, "licenses"):
        cur.execute("""
        CREATE TABLE licenses (
            id INT IDENTITY(1,1) PRIMARY KEY,
            code NVARCHAR(100) NOT NULL UNIQUE,
            institution_id INT NOT NULL,
            client_prefix NVARCHAR(50) NOT NULL,
            role NVARCHAR(50) NOT NULL,
            plan NVARCHAR(50) DEFAULT 'Standard',
            phone NVARCHAR(50),
            dob_year NVARCHAR(10),
            user_ref NVARCHAR(100),
            email NVARCHAR(255),
            two_factor_method NVARCHAR(20) DEFAULT 'email',
            totp_secret NVARCHAR(100),
            db_name NVARCHAR(255) NOT NULL,
            hospital_name NVARCHAR(255) NOT NULL,
            status NVARCHAR(50) DEFAULT 'Active',
            expiry_date NVARCHAR(50),
            created_by NVARCHAR(100) DEFAULT 'admin',
            created_at NVARCHAR(50),
            FOREIGN KEY(institution_id) REFERENCES institutions(id)
        )
        """)
    else:
        for col, coltype in [
            ("email", "NVARCHAR(255)"),
            ("two_factor_method", "NVARCHAR(20) DEFAULT 'email'"),
            ("totp_secret", "NVARCHAR(100)"),
        ]:
            if not _column_exists(cur, "licenses", col):
                cur.execute(f"ALTER TABLE licenses ADD {col} {coltype}")

    if not _table_exists(cur, "admins"):
        cur.execute("""
        CREATE TABLE admins (
            id INT IDENTITY(1,1) PRIMARY KEY,
            username NVARCHAR(100) NOT NULL UNIQUE,
            password_hash NVARCHAR(255) NOT NULL,
            display_name NVARCHAR(255),
            status NVARCHAR(50) DEFAULT 'Active',
            last_login_at NVARCHAR(50),
            created_at NVARCHAR(50)
        )
        """)

    if not _table_exists(cur, "settings"):
        cur.execute("""
        CREATE TABLE settings (
            [key] NVARCHAR(100) PRIMARY KEY,
            value NVARCHAR(MAX)
        )
        """)

    if not _table_exists(cur, "audit_logs"):
        cur.execute("""
        CREATE TABLE audit_logs (
            id INT IDENTITY(1,1) PRIMARY KEY,
            ts NVARCHAR(50) NOT NULL,
            event NVARCHAR(100) NOT NULL,
            role NVARCHAR(50),
            code NVARCHAR(100),
            question NVARCHAR(MAX),
            answer NVARCHAR(MAX),
            tokens_used INT,
            meta NVARCHAR(MAX)
        )
        """)

    conn.commit()
    conn.close()