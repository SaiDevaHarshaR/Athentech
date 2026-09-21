"""
Lockout protection for activation-code guessing on the public widget.
Tracks failed attempts per IP address (not per code — a real attacker
guessing random codes won't reuse the same wrong one, so per-code
tracking wouldn't catch this). Reuses the same Upstash Redis instance
already wired for token limiting.

Threshold: 5 failed attempts within 15 minutes locks that IP out for
15 minutes. The window resets automatically (Redis TTL), no manual
cleanup needed.
"""

import os
from urllib.parse import quote

import requests
from dotenv import load_dotenv

load_dotenv()

_UPSTASH_URL = os.environ.get("UPSTASH_REDIS_REST_URL", "")
_UPSTASH_TOKEN = os.environ.get("UPSTASH_REDIS_REST_TOKEN", "")

_MAX_FAILED_ATTEMPTS = 5
_WINDOW_SECONDS = 15 * 60  # 15 minutes


def _headers():
    return {"Authorization": f"Bearer {_UPSTASH_TOKEN}"}


def _redis_command(*parts) -> dict:
    encoded = [quote(str(p), safe="") for p in parts]
    url = _UPSTASH_URL + "/" + "/".join(encoded)
    resp = requests.get(url, headers=_headers(), timeout=5)
    resp.raise_for_status()
    return resp.json()


def is_locked_out(ip: str) -> dict:
    """
    Call BEFORE validating an activation code. Fails OPEN (not locked
    out) on a Redis error — an infra hiccup should never be the reason
    a legitimate user can't activate their real code.
    """
    key = f"failed_activation:{ip}"
    try:
        result = _redis_command("GET", key)
        count = int(result.get("result") or 0)
        return {"locked_out": count >= _MAX_FAILED_ATTEMPTS, "failed_attempts": count}
    except Exception as e:
        print(f"[activation_lockout] is_locked_out Redis error (failing open): {e}")
        return {"locked_out": False, "failed_attempts": 0}


def record_failed_attempt(ip: str) -> dict:
    """
    Call AFTER an activation code fails validation. Increments the
    counter, sets/refreshes the 15-minute expiry so the window is
    always measured from the MOST RECENT failure — a real attacker
    spacing out guesses to dodge the window gets caught too, since
    each new failure restarts the 15-minute clock.
    """
    key = f"failed_activation:{ip}"
    try:
        result = _redis_command("INCR", key)
        new_count = int(result.get("result", 1))
        _redis_command("EXPIRE", key, str(_WINDOW_SECONDS))
        return {"locked_out": new_count >= _MAX_FAILED_ATTEMPTS, "failed_attempts": new_count}
    except Exception as e:
        print(f"[activation_lockout] record_failed_attempt Redis error (not recorded): {e}")
        return {"locked_out": False, "failed_attempts": 0}


def clear_failed_attempts(ip: str) -> None:
    """Call AFTER a successful activation — a legitimate user shouldn't
    stay one failed guess away from lockout just because they mistyped
    their real code once before getting it right."""
    key = f"failed_activation:{ip}"
    try:
        _redis_command("DEL", key)
    except Exception as e:
        print(f"[activation_lockout] clear_failed_attempts Redis error (harmless, will expire naturally): {e}")