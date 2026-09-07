"""
Encrypts secrets before they ever touch licenses.db (SQLite, plain
file on disk). Previously db_password and smtp_password were stored in
plaintext — anyone with file access to licenses.db (a backup, a copied
file, a compromised server) could read every hospital's real DB login
directly.

Uses Fernet (symmetric, authenticated encryption) from the `cryptography`
library. The encryption key itself lives in .env (ENCRYPTION_KEY) —
NEVER in the database it's protecting, or encryption would be pointless
(anyone with DB access would also have the key sitting right next to it).

Setup:
    python auth/generate_encryption_key.py
    # paste the printed ENCRYPTION_KEY line into your .env

Then run the one-time migration for any secrets that were saved before
this existed:
    python migrate_encrypt_existing_secrets.py
"""

from cryptography.fernet import Fernet, InvalidToken

from config import settings

# Encrypted values are stored with this prefix so reads can tell
# "already encrypted" apart from "legacy plaintext, needs migrating"
# without any ambiguity — Fernet's own token format is base64 and could
# theoretically collide with something else, this prefix can't.
_ENC_PREFIX = "enc::"


def _get_fernet() -> Fernet:
    if not settings.encryption_key:
        raise RuntimeError(
            "ENCRYPTION_KEY is not set. Run auth/generate_encryption_key.py "
            "and add the printed value to your .env file."
        )
    return Fernet(settings.encryption_key.encode())


def encrypt_secret(plaintext: str) -> str:
    """Returns the encrypted value, ready to store in the DB. Empty/None
    values pass through unchanged (nothing to encrypt)."""
    if not plaintext:
        return plaintext
    if plaintext.startswith(_ENC_PREFIX):
        return plaintext  # already encrypted, don't double-encrypt
    token = _get_fernet().encrypt(plaintext.encode())
    return _ENC_PREFIX + token.decode()


def decrypt_secret(stored_value: str) -> str:
    """
    Returns the real plaintext value. Handles legacy plaintext
    transparently (a value saved before encryption existed just gets
    returned as-is) — so this is safe to call on old data without
    requiring the migration script to have run first, though running it
    is still recommended so nothing is left unencrypted at rest.
    """
    if not stored_value:
        return stored_value
    if not stored_value.startswith(_ENC_PREFIX):
        return stored_value  # legacy plaintext, not encrypted yet
    token = stored_value[len(_ENC_PREFIX):]
    try:
        return _get_fernet().decrypt(token.encode()).decode()
    except InvalidToken:
        # Wrong/rotated key, or corrupted data — fail loudly rather than
        # silently returning garbage that looks like a real password.
        raise RuntimeError(
            "Could not decrypt a stored secret — ENCRYPTION_KEY may have "
            "changed since it was saved. Re-enter the affected password(s)."
        )


def is_encrypted(stored_value: str) -> bool:
    return bool(stored_value) and stored_value.startswith(_ENC_PREFIX)