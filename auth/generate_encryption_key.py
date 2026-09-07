"""
Run once to generate your ENCRYPTION_KEY:

    python auth/generate_encryption_key.py

Paste the printed line into your .env file. Losing this key means every
encrypted secret (institution DB passwords, SMTP password) becomes
permanently unrecoverable — back it up somewhere safe, separate from
licenses.db itself (storing them together defeats the purpose).
"""

from cryptography.fernet import Fernet

if __name__ == "__main__":
    key = Fernet.generate_key().decode()
    print("\nAdd this line to your .env file:\n")
    print(f"ENCRYPTION_KEY={key}")
    print("\nBack this key up somewhere separate from licenses.db.")
    print("If you lose it, every encrypted password becomes unrecoverable")
    print("and will need to be re-entered manually.")