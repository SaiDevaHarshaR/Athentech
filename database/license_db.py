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