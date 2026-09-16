"""
Per-institution request limiter, configurable via the admin panel.
SQLite-backed for now — the public functions here (check_and_increment,
get_usage_today, set_plan_limit, get_plan_limit) are the whole interface
the rest of the app touches, so swapping the storage backend to Redis
later only means rewriting the inside of this file, not any caller.
"""

import sqlite3
import threading
from datetime import date

_DB_PATH = "usage_limits.db"
_lock = threading.Lock()

_DEFAULT_PERIOD_TYPE = "day"
_DEFAULT_LIMIT = 15


def _get_conn():
    conn = sqlite3.connect(_DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS plan_limits (
            hospital_id TEXT PRIMARY KEY,
            period_type TEXT NOT NULL DEFAULT 'day',
            limit_value INTEGER NOT NULL DEFAULT 15
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS usage (
            hospital_id TEXT NOT NULL,
            period_key TEXT NOT NULL,
            request_count INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (hospital_id, period_key)
        )
        """
    )
    return conn


def _period_key(period_type: str) -> str:
    today = date.today()
    if period_type == "month":
        return today.strftime("%Y-%m")
    if period_type == "year":
        return today.strftime("%Y")
    return today.isoformat()


def get_plan_limit(hospital_id: str) -> dict:
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT period_type, limit_value FROM plan_limits WHERE hospital_id = ?",
            (hospital_id,),
        ).fetchone()
        if row:
            return {"period_type": row[0], "limit_value": row[1]}
        return {"period_type": _DEFAULT_PERIOD_TYPE, "limit_value": _DEFAULT_LIMIT}
    finally:
        conn.close()


def set_plan_limit(hospital_id: str, period_type: str, limit_value: int) -> dict:
    if period_type not in ("day", "month", "year"):
        return {"error": f"period_type must be 'day', 'month', or 'year', got '{period_type}'."}
    if not isinstance(limit_value, int) or limit_value <= 0:
        return {"error": f"limit_value must be a positive integer, got '{limit_value}'."}

    with _lock:
        conn = _get_conn()
        try:
            conn.execute(
                "INSERT INTO plan_limits (hospital_id, period_type, limit_value) VALUES (?, ?, ?) "
                "ON CONFLICT(hospital_id) DO UPDATE SET period_type = ?, limit_value = ?",
                (hospital_id, period_type, limit_value, period_type, limit_value),
            )
            conn.commit()
            return {"hospital_id": hospital_id, "period_type": period_type, "limit_value": limit_value}
        finally:
            conn.close()


def check_and_increment(hospital_id: str) -> dict:
    plan = get_plan_limit(hospital_id)
    period_type = plan["period_type"]
    limit = plan["limit_value"]
    period_key = _period_key(period_type)

    with _lock:
        conn = _get_conn()
        try:
            row = conn.execute(
                "SELECT request_count FROM usage WHERE hospital_id = ? AND period_key = ?",
                (hospital_id, period_key),
            ).fetchone()
            used = row[0] if row else 0

            if used >= limit:
                return {
                    "allowed": False, "used": used, "limit": limit,
                    "remaining": 0, "period_type": period_type,
                }

            new_count = used + 1
            conn.execute(
                "INSERT INTO usage (hospital_id, period_key, request_count) VALUES (?, ?, ?) "
                "ON CONFLICT(hospital_id, period_key) DO UPDATE SET request_count = ?",
                (hospital_id, period_key, new_count, new_count),
            )
            conn.commit()
            return {
                "allowed": True, "used": new_count, "limit": limit,
                "remaining": limit - new_count, "period_type": period_type,
            }
        finally:
            conn.close()


def get_usage_today(hospital_id: str) -> dict:
    plan = get_plan_limit(hospital_id)
    period_key = _period_key(plan["period_type"])
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT request_count FROM usage WHERE hospital_id = ? AND period_key = ?",
            (hospital_id, period_key),
        ).fetchone()
        return {
            "used": row[0] if row else 0,
            "limit": plan["limit_value"],
            "period_type": plan["period_type"],
            "period_key": period_key,
        }
    finally:
        conn.close()