"""
Provider exhaustion tracker — reuses the same Upstash Redis instance
already wired for token limiting. Marks a provider as exhausted for
the rest of the CURRENT DAY the moment it returns a real quota/rate
error, so the fallback chain skips straight past it on every
subsequent call today, instead of wasting a call re-discovering the
same exhaustion. Naturally resets at midnight — the key is scoped to
today's date, so tomorrow it's just gone.
"""

import os
from datetime import date

import requests
from dotenv import load_dotenv

load_dotenv()

_UPSTASH_URL = os.environ.get("UPSTASH_REDIS_REST_URL", "")
_UPSTASH_TOKEN = os.environ.get("UPSTASH_REDIS_REST_TOKEN", "")

# How long the "exhausted" flag lives, in seconds — a little over 24h
# so it comfortably covers today even if set close to midnight.
_EXHAUSTED_TTL_SECONDS = 26 * 60 * 60


def _headers():
    return {"Authorization": f"Bearer {_UPSTASH_TOKEN}"}


def _redis_command(*parts) -> dict:
    from urllib.parse import quote
    encoded = [quote(str(p), safe="") for p in parts]
    url = _UPSTASH_URL + "/" + "/".join(encoded)
    resp = requests.get(url, headers=_headers(), timeout=5)
    resp.raise_for_status()
    return resp.json()


def _today_key(provider_name: str) -> str:
    return f"exhausted:{provider_name}:{date.today().isoformat()}"


def is_exhausted(provider_name: str) -> bool:
    """
    Check BEFORE attempting a provider. Fails OPEN (says "not exhausted")
    on a Redis error — better to waste one real call to a provider than
    to permanently skip it because of an infra hiccup.
    """
    try:
        result = _redis_command("GET", _today_key(provider_name))
        return result.get("result") is not None
    except Exception as e:
        print(f"[provider_exhaustion] is_exhausted Redis error (failing open, treating as available): {e}")
        return False


def mark_exhausted(provider_name: str, ttl_seconds: int = None) -> None:
    """
    Call this the moment a provider returns a real quota/rate-limit
    error. Sets a flag that expires on its own after ~26h, so tomorrow
    the provider is automatically available again with zero cleanup.
    """
    ttl = ttl_seconds or _EXHAUSTED_TTL_SECONDS
    try:
        _redis_command("SET", _today_key(provider_name), "1")
        _redis_command("EXPIRE", _today_key(provider_name), str(ttl))
        print(f"[provider_exhaustion] Marked '{provider_name}' exhausted for the rest of today.")
    except Exception as e:
        print(f"[provider_exhaustion] mark_exhausted Redis error (not recorded, provider may be retried again): {e}")


def get_available_providers(ordered_provider_names: list) -> list:
    """
    Given the full priority-ordered provider list, returns just the
    ones NOT marked exhausted today, in the same order. If ALL are
    exhausted, returns the full list anyway (better to attempt and
    fail loudly than refuse to even try).
    """
    available = [p for p in ordered_provider_names if not is_exhausted(p)]
    return available if available else ordered_provider_names