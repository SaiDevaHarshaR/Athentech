"""
One-time migration: encrypts any institution db_password or SMTP
password that was saved BEFORE encryption existed (still sitting in
licenses.db as plaintext).

Safe to run more than once — already-encrypted values are detected and
left alone (see auth/secrets_crypto.py's "enc::" prefix marker).

Usage:
    python migrate_encrypt_existing_secrets.py

Requires ENCRYPTION_KEY to already be set in .env — run
auth/generate_encryption_key.py first if you haven't.
"""

from database.license_db import get_conn
from auth.secrets_crypto import encrypt_secret, is_encrypted


def migrate_institution_passwords() -> int:
    conn = get_conn()
    rows = conn.execute("SELECT id, name, db_password FROM institutions").fetchall()

    migrated = 0
    for row in rows:
        pwd = row["db_password"]
        if pwd and not is_encrypted(pwd):
            conn.execute(
                "UPDATE institutions SET db_password = ? WHERE id = ?",
                (encrypt_secret(pwd), row["id"])
            )
            migrated += 1
            print(f"  Encrypted db_password for institution: {row['name']}")

    conn.commit()
    conn.close()
    return migrated


def migrate_smtp_password() -> int:
    conn = get_conn()
    row = conn.execute("SELECT value FROM settings WHERE key = 'smtp_password'").fetchone()

    if row and row["value"] and not is_encrypted(row["value"]):
        conn.execute(
            "UPDATE settings SET value = ? WHERE key = 'smtp_password'",
            (encrypt_secret(row["value"]),)
        )
        conn.commit()
        conn.close()
        print("  Encrypted the SMTP password.")
        return 1

    conn.close()
    return 0


if __name__ == "__main__":
    print("Migrating institution DB passwords...")
    n1 = migrate_institution_passwords()
    print(f"  {n1} institution password(s) encrypted (rest were already encrypted or empty).\n")

    print("Migrating SMTP password...")
    n2 = migrate_smtp_password()
    print(f"  {n2} SMTP password encrypted (0 means it was already encrypted, or not set).\n")

    print("Done. Nothing in licenses.db should be plaintext anymore.")