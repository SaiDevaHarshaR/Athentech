"""
Cloud-hosted (Turso/libSQL) version of database/license_db.py.
Same schema, same public functions, same row["column_name"] access
pattern as the original SQLite version — only get_conn() and the row
wrapper changed. Nothing else in the codebase needs to change.

Credentials from environment variables:
    TURSO_DATABASE_URL
    TURSO_AUTH_TOKEN

Uses an embedded replica (a local file that syncs with the remote
Turso database) — this is the standard, recommended pattern: reads
are fast (local file), writes go to the cloud and sync back. Call
conn.sync() after any write if you need to guarantee the read-back
reflects it immediately (not required for most uses here, since this
process holds the connection continuously).
"""

import os
from datetime import datetime, timedelta

import libsql
from dotenv import load_dotenv

load_dotenv()

_TURSO_URL = os.environ.get("TURSO_DATABASE_URL", "")
_TURSO_TOKEN = os.environ.get("TURSO_AUTH_TOKEN", "")
_LOCAL_REPLICA_PATH = "licenses_replica.db"


class DictRow:
    """Wraps a raw libsql tuple row + column names, mimicking
    sqlite3.Row so existing row["column_name"] access keeps working
    unchanged everywhere else in the codebase."""
    def __init__(self, row, columns):
        self._data = dict(zip(columns, row))

    def __getitem__(self, key):
        return self._data[key]

    def get(self, key, default=None):
        return self._data.get(key, default)

    def keys(self):
        return self._data.keys()

    def items(self):
        return self._data.items()

    def __iter__(self):
        return iter(self._data.values())

    def __repr__(self):
        return f"DictRow({self._data})"


class DictCursor:
    """Wraps a raw libsql cursor so fetchone/fetchall return DictRow
    objects instead of plain tuples — drop-in behavior match for the
    sqlite3.Row-based code this replaces."""
    def __init__(self, raw_cursor):
        self._cursor = raw_cursor

    @property
    def rowcount(self):
        return self._cursor.rowcount

    @property
    def lastrowid(self):
        return self._cursor.lastrowid

    def execute(self, sql, params=()):
        self._cursor.execute(sql, params)
        return self

    def executemany(self, sql, params_list):
        self._cursor.executemany(sql, params_list)
        return self

    def _columns(self):
        return [d[0] for d in self._cursor.description] if self._cursor.description else []

    def fetchone(self):
        row = self._cursor.fetchone()
        if row is None:
            return None
        return DictRow(row, self._columns())

    def fetchall(self):
        columns = self._columns()
        return [DictRow(r, columns) for r in self._cursor.fetchall()]


class DictConn:
    """Wraps a raw libsql connection so .cursor() returns a DictCursor,
    and adds a real .close() (libsql connections don't strictly need
    closing, but existing code calls conn.close() everywhere — keep
    that working as a harmless no-op-if-unsupported call)."""
    def __init__(self, raw_conn):
        self._conn = raw_conn

    def cursor(self):
        return DictCursor(self._conn.cursor())

    def execute(self, sql, params=()):
        # Some existing code calls conn.execute(...) directly (not via
        # a separate cursor) — support that pattern too.
        raw_cursor = self._conn.cursor()
        raw_cursor.execute(sql, params)
        return DictCursor(raw_cursor)

    def executemany(self, sql, params_list):
        raw_cursor = self._conn.cursor()
        raw_cursor.executemany(sql, params_list)
        return DictCursor(raw_cursor)

    def commit(self):
        self._conn.commit()

    def sync(self):
        self._conn.sync()

    def close(self):
        try:
            self._conn.close()
        except Exception:
            pass  # harmless if libsql doesn't require/support explicit close


def get_conn():
    raw_conn = libsql.connect(
        _LOCAL_REPLICA_PATH,
        sync_url=_TURSO_URL,
        auth_token=_TURSO_TOKEN,
    )
    raw_conn.sync()
    return DictConn(raw_conn)


def init_license_db():
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS institutions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        client_prefix TEXT NOT NULL UNIQUE,
        type TEXT,
        city TEXT,
        db_name TEXT NOT NULL,
        db_server TEXT,
        db_user TEXT,
        db_password TEXT,
        status TEXT DEFAULT 'Active',
        created_at TEXT,
        institution_type TEXT DEFAULT 'diagnostic'
    )
    """)

    existing = {row["name"] for row in cur.execute("PRAGMA table_info(institutions)").fetchall()}
    if "db_server" not in existing:
        cur.execute("ALTER TABLE institutions ADD COLUMN db_server TEXT")
    if "db_user" not in existing:
        cur.execute("ALTER TABLE institutions ADD COLUMN db_user TEXT")
    if "db_password" not in existing:
        cur.execute("ALTER TABLE institutions ADD COLUMN db_password TEXT")
    if "institution_type" not in existing:
        cur.execute("ALTER TABLE institutions ADD COLUMN institution_type TEXT DEFAULT 'diagnostic'")

    cur.execute("""
    CREATE TABLE IF NOT EXISTS role_permissions (
    role TEXT PRIMARY KEY,
    tables_csv TEXT NOT NULL
    )
    """)
    defaults = {
    "admin": "patients,admissions,labs,pharmacy,wards,prescriptions,billing",
    "doctor": "patients,admissions,labs,wards",
    "nurse": "patients,admissions,wards,labs",
    "lab_tech": "patients,labs",
    "pharmacist": "patients,pharmacy,prescriptions",
    "reception": "patients,admissions",
    "viewer": "patients,admissions"
    }
    for role, tables in defaults.items():
        cur.execute(
            "INSERT OR IGNORE INTO role_permissions(role, tables_csv) VALUES (?, ?)",
            (role, tables)
        )

    cur.execute("""


    cur.execute("""
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )
    """)
    default_settings = {
        "license_validity_days": "90",
        "normal_mode_enabled": "true",
        "rate_limit_per_minute": "300",
        "extra_blocked_patterns": "",
        "output_redaction_enabled": "true",
        "email_alerts_enabled": "false",
        "webhook_url": "",
        "smtp_host": "",
        "smtp_port": "587",
        "smtp_user": "",
        "smtp_password": "",
        "alert_email_to": "",
    }
    for key, value in default_settings.items():
        cur.execute(
            "INSERT OR IGNORE INTO settings(key, value) VALUES (?, ?)",
            (key, value)
        )

    cur.execute("""
    CREATE TABLE IF NOT EXISTS admins (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        display_name TEXT,
        status TEXT DEFAULT 'Active',
        created_at TEXT,
        last_login_at TEXT
    )
    """)

    conn.commit()
    conn.sync()
    conn.close()


def seed_bootstrap_admin():
    from config import settings as app_settings

    conn = get_conn()
    cur = conn.cursor()
    count = cur.execute("SELECT COUNT(*) AS c FROM admins").fetchone()["c"]

    if count == 0 and app_settings.admin_username and app_settings.admin_password_hash:
        now = datetime.utcnow().isoformat()
        cur.execute(
            "INSERT OR IGNORE INTO admins(username, password_hash, display_name, status, created_at) "
            "VALUES (?, ?, ?, 'Active', ?)",
            (app_settings.admin_username, app_settings.admin_password_hash, "Admin", now)
        )
        conn.commit()
        conn.sync()

    conn.close()


def seed_demo_institutions():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) AS c FROM institutions")
    if cur.fetchone()["c"] == 0:
        now = datetime.utcnow().isoformat()
        cur.executemany("""
            INSERT INTO institutions (name, client_prefix, type, city, db_name, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, [
            ("City Care Hospital", "CCARE", "Hospital", "Hyderabad", "hospital_demo", "Active", now),
            ("Apollo Demo Hospital", "APOLV", "Hospital", "Vizag", "hospital_apollo", "Active", now),
        ])
        conn.commit()
        conn.sync()
    conn.close()