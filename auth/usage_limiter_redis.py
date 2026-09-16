"""
Redis-backed token usage limiter. Same public interface as the SQLite
version (check_budget, record_usage, get_token_plan, set_token_plan) —
nothing else in the app needs to change to use this instead.

Design notes:
- Plan config (period_type, token_limit) is stored as a Redis HASH per
  hospital: "plan:{hospital_id}" -> {period_type, token_limit}.
- Usage is a plain counter key per hospital per period:
  "usage:{hospital_id}:{period_key}" -> integer, incremented atomically
  via INCRBY (no separate read-then-write race condition, unlike the
  SQLite version's lock). Set to auto-expire (Redis TTL) so old period
  keys don't accumulate forever.
- Fail-open on Redis connection errors: if Redis itself is down, budget
  checks default to "allowed" rather than blocking every single
  request in the whole app because of an infra outage. Every fail-open
  path logs loudly so it's never silent.
"""

import os
from datetime import date

import redis

_DEFAULT_PERIOD_TYPE = "day"
_DEFAULT_TOKEN_LIMIT = 5000

# TTL per period type, generous padding so a key never expires while
# still legitimately in use (e.g. a "month" key lives ~35 days, not
# exactly 30, so a long month never gets cut short).
_TTL_SECONDS = {
    "day": 60 * 60 * 24 * 2,       # 2 days
    "month": 60 * 60 * 24 * 35,    # ~35 days
    "year": 60 * 60 * 24 * 370,    # ~370 days
}

_redis_client = None


def _get_client():
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.Redis(
            host=os.environ.get("REDIS_HOST", "localhost"),
            port=int(os.environ.get("REDIS_PORT", 6379)),
            password=os.environ.get("REDIS_PASSWORD"),
            decode_responses=True,
            socket_connect_timeout=3,
            socket_timeout=3,
        )
    return _redis_client


def _period_key(period_type: str) -> str:
    today = date.today()
    if period_type == "month":
        return today.strftime("%Y-%m")
    if period_type == "year":
        return today.strftime("%Y")
    return today.isoformat()


def get_token_plan(hospital_id: str) -> dict:
    try:
        r = _get_client()
        data = r.hgetall(f"plan:{hospital_id}")
        if data:
            return {
                "period_type": data.get("period_type", _DEFAULT_PERIOD_TYPE),
                "token_limit": int(data.get("token_limit", _DEFAULT_TOKEN_LIMIT)),
            }
        return {"period_type": _DEFAULT_PERIOD_TYPE, "token_limit": _DEFAULT_TOKEN_LIMIT}
    except redis.RedisError as e:
        print(f"[usage_limiter] Redis error in get_token_plan (fail-open, using default): {e}")
        return {"period_type": _DEFAULT_PERIOD_TYPE, "token_limit": _DEFAULT_TOKEN_LIMIT}


def set_token_plan(hospital_id: str, period_type: str, token_limit: int) -> dict:
    if period_type not in ("day", "month", "year"):
        return {"error": f"period_type must be 'day', 'month', or 'year', got '{period_type}'."}
    if not isinstance(token_limit, int) or token_limit <= 0:
        return {"error": f"token_limit must be a positive integer, got '{token_limit}'."}

    try:
        r = _get_client()
        r.hset(f"plan:{hospital_id}", mapping={"period_type": period_type, "token_limit": token_limit})
        return {"hospital_id": hospital_id, "period_type": period_type, "token_limit": token_limit}
    except redis.RedisError as e:
        return {"error": f"Could not save plan (Redis error): {e}"}


def check_budget(hospital_id: str) -> dict:
    """
    Call BEFORE invoking the LLM. Returns {"allowed": bool, "used": int,
    "limit": int, "remaining": int, "period_type": str}.
    """
    plan = get_token_plan(hospital_id)
    period_key = _period_key(plan["period_type"])
    limit = plan["token_limit"]

    try:
        r = _get_client()
        used = int(r.get(f"usage:{hospital_id}:{period_key}") or 0)
        return {
            "allowed": used < limit,
            "used": used, "limit": limit,
            "remaining": max(0, limit - used),
            "period_type": plan["period_type"],
        }
    except redis.RedisError as e:
        print(f"[usage_limiter] Redis error in check_budget (fail-open, allowing request): {e}")
        return {"allowed": True, "used": 0, "limit": limit, "remaining": limit, "period_type": plan["period_type"]}


def record_usage(hospital_id: str, tokens_used: int) -> dict:
    """
    Call AFTER a successful LLM call, with the REAL token count. Atomic
    increment via INCRBY — no read-then-write race condition.
    """
    plan = get_token_plan(hospital_id)
    period_key = _period_key(plan["period_type"])
    limit = plan["token_limit"]
    key = f"usage:{hospital_id}:{period_key}"

    if tokens_used <= 0:
        return check_budget(hospital_id)

    try:
        r = _get_client()
        new_total = r.incrby(key, tokens_used)
        ttl = _TTL_SECONDS.get(plan["period_type"], _TTL_SECONDS["day"])
        r.expire(key, ttl)  # (re)set TTL every write — cheap, keeps the key alive while in active use
        return {
            "used": new_total, "limit": limit,
            "remaining": max(0, limit - new_total),
            "period_type": plan["period_type"],
        }
    except redis.RedisError as e:
        print(f"[usage_limiter] Redis error in record_usage (usage NOT recorded this time): {e}")
        return {"used": 0, "limit": limit, "remaining": limit, "period_type": plan["period_type"]}


def get_usage_today(hospital_id: str) -> dict:
    """Read-only — same shape as check_budget, for an admin-panel display."""
    return check_budget(hospital_id)