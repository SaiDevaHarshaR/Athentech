"""
Single-device lock for activation codes. When a code is activated on
one device, a different device trying the same code gets rejected
until the first device logs out (or the session naturally expires).

Genuinely free: reuses the same Upstash Redis instance already wired
for token limiting and activation lockout — no new paid service.

Design: one active fingerprint per activation code, stored with a
generous TTL (refreshed on every request) so a session doesn't linger
forever if someone closes the tab without logging out, but also
doesn't expire mid-conversation.
"""

import os
from urllib.parse import quote

import requests
from dotenv import load_dotenv

load_dotenv()

_UPSTASH_URL = os.environ.get("UPSTASH_REDIS_REST_URL", "")
_UPSTASH_TOKEN = os.environ.get("UPSTASH_REDIS_REST_TOKEN", "")

_SESSION_TTL_SECONDS = 30 * 60  # 30 min of inactivity releases the lock


def _headers():
    return {"Authorization": f"Bearer {_UPSTASH_TOKEN}"}


def _redis_command(*parts) -> dict:
    encoded = [quote(str(p), safe="") for p in parts]
    url = _UPSTASH_URL + "/" + "/".join(encoded)
    resp = requests.get(url, headers=_headers(), timeout=5)
    resp.raise_for_status()
    return resp.json()


def check_and_bind_device(code: str, fingerprint: str) -> dict:
    """
    Call on every activation/validate attempt. Fails OPEN on a Redis
    error — an infra hiccup should never lock a legitimate user out.

    Returns:
        {"allowed": True} — this device now owns the session (either
            it already did, or no session existed yet and this device
            just claimed it).
        {"allowed": False} — a DIFFERENT device currently holds the
            session for this code.
    """
    key = f"device_lock:{code.upper()}"
    try:
        result = _redis_command("GET", key)
        current = result.get("result")

        if current is None or current == fingerprint:
            # No one holds it yet, or this same device already does —
            # claim/refresh it either way.
            _redis_command("SET", key, fingerprint)
            _redis_command("EXPIRE", key, str(_SESSION_TTL_SECONDS))
            return {"allowed": True}

        # A different fingerprint holds it.
        return {"allowed": False}
    except Exception as e:
        print(f"[device_lock] check_and_bind_device Redis error (failing open): {e}")
        return {"allowed": True}


def release_device(code: str) -> None:
    """Call on explicit logout ('exit'/'exit premium') so the code
    becomes usable on another device immediately, rather than waiting
    out the TTL."""
    key = f"device_lock:{code.upper()}"
    try:
        _redis_command("DEL", key)
    except Exception as e:
        print(f"[device_lock] release_device Redis error (harmless, will expire naturally): {e}")