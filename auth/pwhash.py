"""Password hashing for admin accounts: PBKDF2-SHA256 with a per-password salt.
Old unsalted SHA-256 hashes still verify and are upgraded on the next successful login."""
import hashlib
import hmac
import os

_ITER = 240_000
_PREFIX = "pbkdf2$"


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _ITER)
    return f"{_PREFIX}{_ITER}${salt.hex()}${dk.hex()}"


def is_legacy(stored: str) -> bool:
    return not str(stored or "").startswith(_PREFIX)


def verify_password(stored: str, password: str) -> bool:
    stored = str(stored or "")
    if stored.startswith(_PREFIX):
        try:
            _, it, salt, dk = stored.split("$")
            calc = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(it))
            return hmac.compare_digest(calc.hex(), dk)
        except Exception:
            return False
    return hmac.compare_digest(stored, hashlib.sha256(password.encode()).hexdigest())
