"""
Run this once to generate the values for your .env file:

    python auth/generate_admin_hash.py

It will ask for your desired admin password (input hidden) and print:
    ADMIN_USERNAME=admin
    ADMIN_PASSWORD_HASH=<sha256 hex digest>
    ADMIN_SECRET_KEY=<random 64-char key>

Paste those three lines into your .env file. Never commit .env.
"""

import getpass
import hashlib
import secrets


def main():
    username = input("Admin username [admin]: ").strip() or "admin"
    password = getpass.getpass("Admin password: ")
    confirm = getpass.getpass("Confirm password: ")

    if password != confirm:
        print("Passwords did not match. Aborting.")
        return

    if len(password) < 10:
        print("Warning: use a longer password (10+ chars) for a production admin account.")

    pw_hash = hashlib.sha256(password.encode()).hexdigest()
    secret_key = secrets.token_hex(32)

    print("\nAdd these lines to your .env file:\n")
    print(f"ADMIN_USERNAME={username}")
    print(f"ADMIN_PASSWORD_HASH={pw_hash}")
    print(f"ADMIN_SECRET_KEY={secret_key}")


if __name__ == "__main__":
    main()
