"""
Daily request limiter — per-hospital (per activation code), resets at
midnight server time. Free tier: 15 requests/day. Paid tier: configurable,
default 500/day (effectively unlimited for normal use, but still capped
to prevent runaway abuse).

Uses a small local SQLite file (separate from the main hospital DB —
this is internal usage tracking, not hospital data). Safe to merge into
an existing license/activation database later if one exists; this is a
self-contained, working version deployable right now.
"""

import sqlite3
import threading
from datetime import date

_DB_PATH = "usage_limits.db"
_lock = threading.Lock()

FREE_TIER_DAILY_LIMIT = 15
PAID_TIER_DAILY_LIMIT = 500  # generous default; adjust per contract if needed


def _get_conn():
    conn = sqlite3.connect(_DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS usage (
            hospital_id TEXT NOT NULL,
            usage_date TEXT NOT NULL,
            request_count INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (hospital_id, usage_date)
        )
        """
    )
    return conn


def check_and_increment(hospital_id: str, plan_tier: str = "free") -> dict:
    """
    Call this ONCE per incoming request, before processing it.

    Returns:
        {"allowed": bool, "used": int, "limit": int, "remaining": int}

    If allowed=False, the request should be rejected with a clear
    message — the count is NOT incremented for a rejected request.
    """
    limit = PAID_TIER_DAILY_LIMIT if plan_tier == "paid" else FREE_TIER_DAILY_LIMIT
    today = date.today().isoformat()

    with _lock:
        conn = _get_conn()
        try:
            cursor = conn.execute(
                "SELECT request_count FROM usage WHERE hospital_id = ? AND usage_date = ?",
                (hospital_id, today),
            )
            row = cursor.fetchone()
            used = row[0] if row else 0

            if used >= limit:
                return {"allowed": False, "used": used, "limit": limit, "remaining": 0}

            new_count = used + 1
            conn.execute(
                "INSERT INTO usage (hospital_id, usage_date, request_count) VALUES (?, ?, ?) "
                "ON CONFLICT(hospital_id, usage_date) DO UPDATE SET request_count = ?",
                (hospital_id, today, new_count, new_count),
            )
            conn.commit()
            return {
                "allowed": True, "used": new_count, "limit": limit,
                "remaining": limit - new_count,
            }
        finally:
            conn.close()


def get_usage_today(hospital_id: str) -> dict:
    """Read-only check, doesn't increment — for a status/usage display."""
    today = date.today().isoformat()
    conn = _get_conn()
    try:
        cursor = conn.execute(
            "SELECT request_count FROM usage WHERE hospital_id = ? AND usage_date = ?",
            (hospital_id, today),
        )
        row = cursor.fetchone()
        return {"used": row[0] if row else 0, "date": today}
    finally:
        conn.close()