"""
Token-based usage limiter. Unlike a request-count limiter, this tracks
REAL token consumption (input + output) per LLM call, accumulated per
institution per period. Intent-answered questions (agent/intents.py)
never touch the LLM at all, so they cost zero tokens and are correctly
never counted here — only genuine LLM usage counts against the budget.

Two-step usage per request:
1. check_budget(hospital_id) BEFORE calling the LLM — refuses the
   request outright if the institution is already at/over budget.
   (Can't know the exact token cost of a not-yet-made call in advance,
   so this is a "do they have ANY room left" gate, not a precise
   pre-check of this specific request's cost.)
2. record_usage(hospital_id, tokens_used) AFTER the LLM call succeeds
   — adds the REAL token count from the response's usage metadata to
   the institution's running total for the current period.
"""

import sqlite3
import threading
from datetime import date

_DB_PATH = "usage_limits.db"
_lock = threading.Lock()

_DEFAULT_PERIOD_TYPE = "day"
_DEFAULT_TOKEN_LIMIT = 5000


def _get_conn():
    conn = sqlite3.connect(_DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS token_plan_limits (
            hospital_id TEXT PRIMARY KEY,
            period_type TEXT NOT NULL DEFAULT 'day',
            token_limit INTEGER NOT NULL DEFAULT 5000
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS token_usage (
            hospital_id TEXT NOT NULL,
            period_key TEXT NOT NULL,
            tokens_used INTEGER NOT NULL DEFAULT 0,
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


def get_token_plan(hospital_id: str) -> dict:
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT period_type, token_limit FROM token_plan_limits WHERE hospital_id = ?",
            (hospital_id,),
        ).fetchone()
        if row:
            return {"period_type": row[0], "token_limit": row[1]}
        return {"period_type": _DEFAULT_PERIOD_TYPE, "token_limit": _DEFAULT_TOKEN_LIMIT}
    finally:
        conn.close()


def set_token_plan(hospital_id: str, period_type: str, token_limit: int) -> dict:
    if period_type not in ("day", "month", "year"):
        return {"error": f"period_type must be 'day', 'month', or 'year', got '{period_type}'."}
    if not isinstance(token_limit, int) or token_limit <= 0:
        return {"error": f"token_limit must be a positive integer, got '{token_limit}'."}

    with _lock:
        conn = _get_conn()
        try:
            conn.execute(
                "INSERT INTO token_plan_limits (hospital_id, period_type, token_limit) VALUES (?, ?, ?) "
                "ON CONFLICT(hospital_id) DO UPDATE SET period_type = ?, token_limit = ?",
                (hospital_id, period_type, token_limit, period_type, token_limit),
            )
            conn.commit()
            return {"hospital_id": hospital_id, "period_type": period_type, "token_limit": token_limit}
        finally:
            conn.close()


def check_budget(hospital_id: str) -> dict:
    """
    Call BEFORE invoking the LLM. Returns {"allowed": bool, "used": int,
    "limit": int, "remaining": int, "period_type": str}. Does NOT
    increment anything — this is a pure read, since the real cost isn't
    known until after the call. If not allowed, skip the LLM call and
    return the limiter's message instead.
    """
    plan = get_token_plan(hospital_id)
    period_key = _period_key(plan["period_type"])
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT tokens_used FROM token_usage WHERE hospital_id = ? AND period_key = ?",
            (hospital_id, period_key),
        ).fetchone()
        used = row[0] if row else 0
        limit = plan["token_limit"]
        return {
            "allowed": used < limit,
            "used": used, "limit": limit,
            "remaining": max(0, limit - used),
            "period_type": plan["period_type"],
        }
    finally:
        conn.close()


def record_usage(hospital_id: str, tokens_used: int) -> dict:
    """
    Call AFTER a successful LLM call, with the REAL token count from
    the response's usage metadata (input + output tokens combined).
    Adds to the running total for the current period.
    """
    if tokens_used <= 0:
        return check_budget(hospital_id)  # nothing to add, just report current state

    plan = get_token_plan(hospital_id)
    period_key = _period_key(plan["period_type"])

    with _lock:
        conn = _get_conn()
        try:
            row = conn.execute(
                "SELECT tokens_used FROM token_usage WHERE hospital_id = ? AND period_key = ?",
                (hospital_id, period_key),
            ).fetchone()
            current = row[0] if row else 0
            new_total = current + tokens_used

            conn.execute(
                "INSERT INTO token_usage (hospital_id, period_key, tokens_used) VALUES (?, ?, ?) "
                "ON CONFLICT(hospital_id, period_key) DO UPDATE SET tokens_used = ?",
                (hospital_id, period_key, new_total, new_total),
            )
            conn.commit()
            limit = plan["token_limit"]
            return {
                "used": new_total, "limit": limit,
                "remaining": max(0, limit - new_total),
                "period_type": plan["period_type"],
            }
        finally:
            conn.close()


def get_usage_today(hospital_id: str) -> dict:
    """Read-only — same shape as check_budget, for an admin-panel display."""
    return check_budget(hospital_id)