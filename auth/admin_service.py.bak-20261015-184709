"""
Real multi-admin accounts, replacing the single shared admin/password.

Each admin has their own username + password, so every admin action can
be attributed to the actual person who did it (see the audit() calls in
main.py for institution/license/settings changes) instead of everything
just being "Admin".
"""

import hashlib
import hmac
from datetime import datetime

from database.license_db import get_conn


def _hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def list_admins() -> list:
    conn = get_conn()
    rows = conn.execute(
        "SELECT id, username, display_name, status, created_at, last_login_at FROM admins ORDER BY id ASC"
    ).fetchall()
    conn.close()
    # Never return password_hash, even to other admins.
    return [dict(r) for r in rows]


def create_admin(username: str, password: str, display_name: str = "") -> dict:
    username = username.strip()
    if not username:
        raise ValueError("Username is required")
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters")

    conn = get_conn()
    cur = conn.cursor()

    existing = cur.execute("SELECT id FROM admins WHERE username = ?", (username,)).fetchone()
    if existing:
        conn.close()
        raise ValueError(f"Username '{username}' already exists")

    now = datetime.utcnow().isoformat()
    cur.execute(
        "INSERT INTO admins(username, password_hash, display_name, status, created_at) "
        "VALUES (?, ?, ?, 'Active', ?)",
        (username, _hash_password(password), display_name or username, now)
    )
    conn.commit()
    admin_id = cur.lastrowid
    conn.close()

    return {"id": admin_id, "username": username, "display_name": display_name or username, "status": "Active"}


def set_admin_status(username: str, status: str) -> bool:
    if status not in ("Active", "Inactive"):
        raise ValueError("Invalid status")

    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE admins SET status = ? WHERE username = ?", (status, username))
    conn.commit()
    changed = cur.rowcount
    conn.close()
    return changed > 0


def change_admin_password(username: str, new_password: str) -> bool:
    if len(new_password) < 8:
        raise ValueError("Password must be at least 8 characters")

    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "UPDATE admins SET password_hash = ? WHERE username = ?",
        (_hash_password(new_password), username)
    )
    conn.commit()
    changed = cur.rowcount
    conn.close()
    return changed > 0


def verify_admin_login(username: str, password: str) -> bool:
    """
    Checks credentials against the real admins table. On success, also
    stamps last_login_at so 'who's actually using this' is visible in
    the admin list, not just a static roster.
    """
    conn = get_conn()
    row = conn.execute(
        "SELECT password_hash, status FROM admins WHERE username = ?", (username,)
    ).fetchone()

    if not row or row["status"] != "Active":
        conn.close()
        return False

    expected_hash = row["password_hash"]
    actual_hash = _hash_password(password)
    ok = hmac.compare_digest(expected_hash, actual_hash)

    if ok:
        conn.execute(
            "UPDATE admins SET last_login_at = ? WHERE username = ?",
            (datetime.utcnow().isoformat(), username)
        )
        conn.commit()

    conn.close()
    return ok


def admin_exists(username: str) -> bool:
    conn = get_conn()
    row = conn.execute("SELECT 1 FROM admins WHERE username = ?", (username,)).fetchone()
    conn.close()
    return row is not None
