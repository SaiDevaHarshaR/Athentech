"""
OpenAI usage/spend tracking for the admin dashboard. Uses OpenAI's real
Usage API (organization/usage/completions), which requires a separate
Admin API key — NOT the regular key used for chat completions.

Genuinely free: creating an Admin key costs nothing, and reading usage
data through it costs nothing either (it's a reporting endpoint, not
a completion request).

Real limitation to keep in mind: OpenAI has no fixed daily/monthly
token QUOTA the way Groq does — it's pure pay-as-you-go against a
dollar spending limit you set yourself. So this reports real usage
over time (tokens, requests, spend), not a "X out of Y" percentage —
there's no Y to divide against on OpenAI's side.

Requires OPENAI_ADMIN_KEY in .env — separate from OPENAI_API_KEY.
Create one at platform.openai.com/settings/organization/admin-keys
(must be the Organization Owner).
"""

import os
import time

import requests
from dotenv import load_dotenv

load_dotenv()

_OPENAI_ADMIN_KEY = os.environ.get("OPENAI_ADMIN_KEY", "")


def get_openai_usage(days_back: int = 30) -> dict:
    """
    Real usage pulled directly from OpenAI's Usage API. Returns a
    summary (total tokens, total requests, per-day breakdown) rather
    than a percentage, since OpenAI has no fixed quota to compare
    against.
    """
    if not _OPENAI_ADMIN_KEY:
        return {
            "available": False,
            "reason": "OPENAI_ADMIN_KEY not set in .env. Create one at "
                       "platform.openai.com/settings/organization/admin-keys "
                       "(requires Organization Owner access).",
        }

    start_time = int(time.time()) - (days_back * 24 * 60 * 60)

    try:
        resp = requests.get(
            "https://api.openai.com/v1/organization/usage/completions",
            headers={"Authorization": f"Bearer {_OPENAI_ADMIN_KEY}"},
            params={"start_time": start_time, "bucket_width": "1d", "limit": days_back},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        return {"available": False, "reason": f"Could not reach OpenAI's Usage API: {e}"}

    total_input_tokens = 0
    total_output_tokens = 0
    total_requests = 0
    daily = []

    for bucket in data.get("data", []):
        bucket_input = 0
        bucket_output = 0
        bucket_requests = 0
        for result in bucket.get("results", []):
            bucket_input += result.get("input_tokens", 0) or 0
            bucket_output += result.get("output_tokens", 0) or 0
            bucket_requests += result.get("num_model_requests", 0) or 0

        total_input_tokens += bucket_input
        total_output_tokens += bucket_output
        total_requests += bucket_requests

        daily.append({
            "start_time": bucket.get("start_time"),
            "input_tokens": bucket_input,
            "output_tokens": bucket_output,
            "total_tokens": bucket_input + bucket_output,
            "requests": bucket_requests,
        })

    return {
        "available": True,
        "period_days": days_back,
        "total_input_tokens": total_input_tokens,
        "total_output_tokens": total_output_tokens,
        "total_tokens": total_input_tokens + total_output_tokens,
        "total_requests": total_requests,
        "daily": daily,
    }


def get_openai_credit_balance() -> dict:
    """
    Real prepaid credit balance — separate from the Usage/Costs APIs,
    and a genuinely less-documented/older endpoint. Honest limitation:
    this may not work reliably for every account; test against the
    real account before trusting it in production.
    """
    if not _OPENAI_ADMIN_KEY:
        return {"available": False, "reason": "OPENAI_ADMIN_KEY not set."}

    try:
        resp = requests.get(
            "https://api.openai.com/v1/dashboard/billing/credit_grants",
            headers={"Authorization": f"Bearer {_OPENAI_ADMIN_KEY}"},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        return {
            "available": True,
            "total_granted": data.get("total_granted"),
            "total_used": data.get("total_used"),
            "total_available": data.get("total_available"),
        }
    except Exception as e:
        return {"available": False, "reason": f"Could not fetch credit balance: {e}"}


def get_openai_costs(days_back: int = 30) -> dict:
    """
    Real USD spend from OpenAI's Costs API — separate endpoint from
    usage/completions, same Admin key.
    """
    if not _OPENAI_ADMIN_KEY:
        return {"available": False, "reason": "OPENAI_ADMIN_KEY not set."}

    start_time = int(time.time()) - (days_back * 24 * 60 * 60)

    try:
        resp = requests.get(
            "https://api.openai.com/v1/organization/costs",
            headers={"Authorization": f"Bearer {_OPENAI_ADMIN_KEY}"},
            params={"start_time": start_time, "limit": days_back},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        return {"available": False, "reason": f"Could not reach OpenAI's Costs API: {e}"}

    total_usd = 0.0
    for bucket in data.get("data", []):
        for result in bucket.get("results", []):
            amount = result.get("amount", {})
            total_usd += amount.get("value", 0) or 0

    return {"available": True, "total_usd": round(total_usd, 2), "period_days": days_back}