"""
OpenRouter quota checker. OpenRouter has a real, dedicated endpoint
for this — GET /api/v1/auth/key — confirmed across multiple
independent sources. Returns credit usage/limit and rate limit info
for the current key directly, no need to make a completion request.
"""

import os

import requests
from dotenv import load_dotenv

load_dotenv()

_OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")


def get_openrouter_quota() -> dict:
    if not _OPENROUTER_API_KEY:
        return {"available": False, "reason": "OPENROUTER_API_KEY not set."}

    try:
        resp = requests.get(
            "https://openrouter.ai/api/v1/auth/key",
            headers={"Authorization": f"Bearer {_OPENROUTER_API_KEY}"},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json().get("data", {})

        credits_used = data.get("usage", 0) or 0
        credit_limit = data.get("limit")  # None means unlimited (paid, no cap)
        is_free_tier = data.get("is_free_tier", True)
        rate_limit = data.get("rate_limit", {})

        result = {
            "available": True,
            "provider": "openrouter",
            "is_free_tier": is_free_tier,
            "credits_used": credits_used,
            "credit_limit": credit_limit,
            "rate_limit_requests": rate_limit.get("requests"),
            "rate_limit_interval": rate_limit.get("interval"),
        }

        if credit_limit:
            result["pct_used"] = round((credits_used / credit_limit) * 100)

        return result
    except Exception as e:
        return {"available": False, "reason": f"Could not reach OpenRouter: {e}"}