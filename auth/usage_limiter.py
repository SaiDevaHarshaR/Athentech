"""
Token-based usage limiter, backed by Upstash Redis (REST API).
Credentials from environment variables:
    UPSTASH_REDIS_REST_URL
    UPSTASH_REDIS_REST_TOKEN
"""
import json
import os
from datetime import date
from urllib.parse import quote

import requests
from dotenv import load_dotenv

load_dotenv()

_UPSTASH_URL = os.environ.get("UPSTASH_REDIS_REST_URL", "")
_UPSTASH_TOKEN = os.environ.get("UPSTASH_REDIS_REST_TOKEN", "")
import json
import os
from datetime import date
from urllib.parse import quote

import requests

_UPSTASH_URL = os.environ.get("UPSTASH_REDIS_REST_URL", "")
_UPSTASH_TOKEN = os.environ.get("UPSTASH_REDIS_REST_TOKEN", "")

_DEFAULT_PERIOD_TYPE = "day"
_DEFAULT_TOKEN_LIMIT = 5000


def _headers():
    return {"Authorization": f"Bearer {_UPSTASH_TOKEN}"}


def _redis_command(*parts) -> dict:
    encoded = [quote(str(p), safe="") for p in parts]
    url = _UPSTASH_URL + "/" + "/".join(encoded)
    resp = requests.get(url, headers=_headers(), timeout=5)
    resp.raise_for_status()
    return resp.json()


def _period_key(period_type: str) -> str:
    today = date.today()
    if period_type == "month":
        return today.strftime("%Y-%m")
    if period_type == "year":
        return today.strftime("%Y")
    return today.isoformat()


def get_token_plan(hospital_id: str) -> dict:
    try:
        result = _redis_command("GET", f"plan:{hospital_id}")
        raw = result.get("result")
        if raw:
            return json.loads(raw)
        return {"period_type": _DEFAULT_PERIOD_TYPE, "token_limit": _DEFAULT_TOKEN_LIMIT}
    except Exception as e:
        print(f"[usage_limiter] get_token_plan error (fail-open to default): {e}")
        return {"period_type": _DEFAULT_PERIOD_TYPE, "token_limit": _DEFAULT_TOKEN_LIMIT}


def set_token_plan(hospital_id: str, period_type: str, token_limit: int) -> dict:
    if period_type not in ("day", "month", "year"):
        return {"error": f"period_type must be 'day', 'month', or 'year', got '{period_type}'."}
    if not isinstance(token_limit, int) or token_limit <= 0:
        return {"error": f"token_limit must be a positive integer, got '{token_limit}'."}
    try:
        payload = json.dumps({"period_type": period_type, "token_limit": token_limit})
        _redis_command("SET", f"plan:{hospital_id}", payload)
        return {"hospital_id": hospital_id, "period_type": period_type, "token_limit": token_limit}
    except Exception as e:
        return {"error": f"Could not save plan: {e}"}


def check_budget(hospital_id: str) -> dict:
    plan = get_token_plan(hospital_id)
    period_key = _period_key(plan["period_type"])
    limit = plan["token_limit"]
    try:
        result = _redis_command("GET", f"usage:{hospital_id}:{period_key}")
        used = int(result.get("result") or 0)
        return {"allowed": used < limit, "used": used, "limit": limit,
                "remaining": max(0, limit - used), "period_type": plan["period_type"]}
    except Exception as e:
        print(f"[usage_limiter] check_budget error (fail-open, allowing): {e}")
        return {"allowed": True, "used": 0, "limit": limit, "remaining": limit, "period_type": plan["period_type"]}


def record_usage(hospital_id: str, tokens_used: int) -> dict:
    if tokens_used <= 0:
        return check_budget(hospital_id)
    plan = get_token_plan(hospital_id)
    period_key = _period_key(plan["period_type"])
    limit = plan["token_limit"]
    try:
        result = _redis_command("INCRBY", f"usage:{hospital_id}:{period_key}", str(tokens_used))
        new_total = int(result.get("result", tokens_used))
        return {"used": new_total, "limit": limit,
                "remaining": max(0, limit - new_total), "period_type": plan["period_type"]}
    except Exception as e:
        print(f"[usage_limiter] record_usage error (not recorded): {e}")
        return {"used": 0, "limit": limit, "remaining": limit, "period_type": plan["period_type"]}


def get_usage_today(hospital_id: str) -> dict:
    return check_budget(hospital_id)