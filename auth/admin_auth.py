"""
Minimal admin authentication for the Sahasra admin panel.

Uses an HMAC-signed, time-limited token — no external auth library needed.
This is NOT a replacement for a real identity provider long-term, but it
closes the "anyone with the URL can generate/revoke licenses" hole with
something simple and auditable.

Setup:
1. Run `python auth/generate_admin_hash.py` and follow the prompts.
   It prints ADMIN_PASSWORD_HASH and ADMIN_SECRET_KEY values.
2. Put them in your .env file:
     ADMIN_USERNAME=admin
     ADMIN_PASSWORD_HASH=<printed hash>
     ADMIN_SECRET_KEY=<printed random key>
3. Restart the API. POST /admin/login with {"username": "...", "password": "..."}
   to get a token, then send it as `Authorization: Bearer <token>` on every
   /admin/* request.
"""

import hmac
import hashlib
import base64
import time

from fastapi import Header, HTTPException

from config import settings

TOKEN_TTL_SECONDS = 8 * 60 * 60  # 8 hour admin session


def _sign(payload: str) -> str:
    if not settings.admin_secret_key:
        # Fail loudly rather than silently signing with an empty/default key.
        raise RuntimeError(
            "ADMIN_SECRET_KEY is not set. Run auth/generate_admin_hash.py "
            "and add the values to your .env file."
        )
    return hmac.new(
        settings.admin_secret_key.encode(),
        payload.encode(),
        hashlib.sha256,
    ).hexdigest()


def create_admin_token(username: str) -> str:
    issued_at = str(int(time.time()))
    payload = f"{username}:{issued_at}"
    sig = _sign(payload)
    raw = f"{payload}:{sig}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def verify_admin_token(token: str) -> str:
    try:
        raw = base64.urlsafe_b64decode(token.encode()).decode()
        username, issued_at, sig = raw.rsplit(":", 2)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid admin session")

    expected_sig = _sign(f"{username}:{issued_at}")
    if not hmac.compare_digest(sig, expected_sig):
        raise HTTPException(status_code=401, detail="Invalid admin session")

    if time.time() - int(issued_at) > TOKEN_TTL_SECONDS:
        raise HTTPException(status_code=401, detail="Admin session expired, please log in again")

    return username


def check_admin_credentials(username: str, password: str) -> bool:
    if not settings.admin_password_hash:
        raise RuntimeError(
            "ADMIN_PASSWORD_HASH is not set. Run auth/generate_admin_hash.py "
            "and add the values to your .env file."
        )
    username_ok = hmac.compare_digest(username, settings.admin_username)
    pw_hash = hashlib.sha256(password.encode()).hexdigest()
    password_ok = hmac.compare_digest(pw_hash, settings.admin_password_hash)
    return username_ok and password_ok


def require_admin(authorization: str = Header(default=None)) -> str:
    """
    FastAPI dependency. Add `admin: str = Depends(require_admin)` to any
    route that should only be reachable by a logged-in admin.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing admin session")
    token = authorization.split(" ", 1)[1]
    return verify_admin_token(token)
