"""
Groq quota checker. Groq exposes real rate-limit info via response
headers on every API call — confirmed real, documented behavior,
unlike OpenAI's pay-as-you-go model which has no such concept.

Honest limitation: the token-related headers
(x-ratelimit-limit-tokens / remaining-tokens) report your PER-MINUTE
(TPM) limit, not the per-day (TPD) limit you've actually been hitting
in production (the "200000 daily" errors). Groq's headers don't
directly expose remaining tokens for the day — only remaining
REQUESTS for the day (x-ratelimit-remaining-requests is documented as
"Always refers to Requests Per Day"). So this reports two genuinely
different, real numbers: your per-minute token headroom, and your
per-day request headroom — not a single daily-token percentage.

Makes a minimal, cheap request (1 token) purely to read the headers,
not to get a real completion — this costs a negligible amount of your
actual budget just to check it.
"""

import os

import requests
from dotenv import load_dotenv

load_dotenv()

_GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")


def get_groq_quota() -> dict:
    if not _GROQ_API_KEY:
        return {"available": False, "reason": "GROQ_API_KEY not set."}

    try:
        resp = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {_GROQ_API_KEY}", "Content-Type": "application/json"},
            json={
                "model": "openai/gpt-oss-20b",
                "messages": [{"role": "user", "content": "hi"}],
                "max_tokens": 1,
            },
            timeout=10,
        )
        headers = resp.headers

        limit_tokens_per_minute = headers.get("x-ratelimit-limit-tokens")
        remaining_tokens_per_minute = headers.get("x-ratelimit-remaining-tokens")
        limit_requests_per_day = headers.get("x-ratelimit-limit-requests")
        remaining_requests_per_day = headers.get("x-ratelimit-remaining-requests")

        if limit_tokens_per_minute is None:
            return {"available": False, "reason": "Groq response had no rate-limit headers."}

        limit_tokens_per_minute = int(limit_tokens_per_minute)
        remaining_tokens_per_minute = int(remaining_tokens_per_minute)

        result = {
            "available": True,
            "provider": "groq",
            "tpm_limit": limit_tokens_per_minute,
            "tpm_remaining": remaining_tokens_per_minute,
            "tpm_pct_used": round(
                ((limit_tokens_per_minute - remaining_tokens_per_minute) / limit_tokens_per_minute) * 100
            ) if limit_tokens_per_minute else 0,
        }

        if limit_requests_per_day and remaining_requests_per_day:
            rpd_limit = int(limit_requests_per_day)
            rpd_remaining = int(remaining_requests_per_day)
            result["rpd_limit"] = rpd_limit
            result["rpd_remaining"] = rpd_remaining
            result["rpd_pct_used"] = round(((rpd_limit - rpd_remaining) / rpd_limit) * 100) if rpd_limit else 0

        return result
    except Exception as e:
        return {"available": False, "reason": f"Could not reach Groq: {e}"}