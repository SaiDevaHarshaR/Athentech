import sqlite3
from datetime import datetime, timedelta
import os

DB_PATH = "licenses.db"

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

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
        status TEXT DEFAULT 'Active',
        created_at TEXT
    )
    """)
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
    CREATE TABLE IF NOT EXISTS licenses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT NOT NULL UNIQUE,
        institution_id INTEGER NOT NULL,
        client_prefix TEXT NOT NULL,
        role TEXT NOT NULL,
        plan TEXT DEFAULT 'Standard',
        phone TEXT,
        dob_year TEXT,
        user_ref TEXT,
        db_name TEXT NOT NULL,
        hospital_name TEXT NOT NULL,
        status TEXT DEFAULT 'Active',
        expiry_date TEXT,
        created_by TEXT DEFAULT 'admin',
        created_at TEXT,
        FOREIGN KEY(institution_id) REFERENCES institutions(id)
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )
    """)
    # Defaults match what was previously hardcoded in main.py/guardrails.py,
    # so applying no changes here keeps existing behavior identical.
    default_settings = {
        "license_validity_days": "90",
        "normal_mode_enabled": "true",     # allow non-premium web-search chat
        "rate_limit_per_minute": "300",
        "extra_blocked_patterns": "",      # comma-separated, ADDED to the built-in guardrail patterns
        "output_redaction_enabled": "true",
        "email_alerts_enabled": "false",
        "webhook_url": "",
        # SMTP config for actually sending the email alerts above.
        # Without these, email_alerts_enabled=true does nothing — there's
        # no delivery mechanism to toggle on.
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
    conn.close()


def seed_bootstrap_admin():
    """
    One-time migration: if the admins table is empty but a legacy
    single-admin credential exists in .env (ADMIN_USERNAME +
    ADMIN_PASSWORD_HASH from the old single-admin setup), copy it into
    the real admins table so existing installs don't get locked out when
    upgrading to multi-admin support. New installs should just use
    auth/generate_admin_hash.py or POST /admin/users to create the first
    real account instead of relying on this fallback.
    """
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
    conn.close()