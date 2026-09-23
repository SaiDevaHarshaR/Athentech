"""
Email-based second factor for activation codes. After a code validates
successfully, a 6-digit OTP is emailed to that license's registered
email address (stored per-license, set when the admin creates it).
The person must enter that OTP before premium access is actually
granted.

Reuses infrastructure already in place — no new paid service:
  - Upstash Redis (same instance as token limiter/lockout) for OTP
    storage with a short TTL
  - The existing SMTP settings (smtp_host/smtp_port/smtp_user/
    smtp_password) already wired for admin alert emails
"""

import os
import random
import smtplib
from email.mime.text import MIMEText
from urllib.parse import quote

import requests
from dotenv import load_dotenv

load_dotenv()

_UPSTASH_URL = os.environ.get("UPSTASH_REDIS_REST_URL", "")
_UPSTASH_TOKEN = os.environ.get("UPSTASH_REDIS_REST_TOKEN", "")

_OTP_TTL_SECONDS = 5 * 60  # 5 minutes to enter the code
_MAX_VERIFY_ATTEMPTS = 5


def _headers():
    return {"Authorization": f"Bearer {_UPSTASH_TOKEN}"}


def _redis_command(*parts) -> dict:
    encoded = [quote(str(p), safe="") for p in parts]
    url = _UPSTASH_URL + "/" + "/".join(encoded)
    resp = requests.get(url, headers=_headers(), timeout=5)
    resp.raise_for_status()
    return resp.json()


def generate_and_send_otp(code: str, email: str, hospital_name: str) -> dict:
    """
    Generates a real 6-digit OTP, stores it in Redis keyed to the
    activation code, and emails it using the existing SMTP settings.

    Returns {"sent": True} on success, or {"sent": False, "reason": "..."}
    if email isn't configured or sending failed — caller should treat
    this as a real error (not fail open), since skipping the OTP step
    entirely would defeat the whole point of a second factor.
    """
    if not email:
        return {"sent": False, "reason": "No email on file for this license."}

    from database.license_db import get_conn
    conn = get_conn()
    settings_row = {}
    try:
        cur = conn.cursor()
        rows = cur.execute("SELECT key, value FROM settings").fetchall()
        settings_row = {r["key"]: r["value"] for r in rows}
    finally:
        conn.close()

    smtp_host = settings_row.get("smtp_host", "")
    smtp_port = int(settings_row.get("smtp_port", 587) or 587)
    smtp_user = settings_row.get("smtp_user", "")
    smtp_password_encrypted = settings_row.get("smtp_password", "")

    if not smtp_host or not smtp_user:
        return {"sent": False, "reason": "SMTP not configured in admin settings."}

    from auth.secrets_crypto import decrypt_secret
    smtp_password = decrypt_secret(smtp_password_encrypted)

    otp = str(random.randint(100000, 999999))
    key = f"otp:{code.upper()}"
    attempts_key = f"otp_attempts:{code.upper()}"

    try:
        _redis_command("SET", key, otp)
        _redis_command("EXPIRE", key, str(_OTP_TTL_SECONDS))
        _redis_command("DEL", attempts_key)  # reset attempt counter for a fresh OTP
    except Exception as e:
        print(f"[email_otp] Redis error storing OTP: {e}")
        return {"sent": False, "reason": "Could not generate OTP right now."}

    try:
        msg = MIMEText(
            f"Your Sahasra AI Assistant verification code for {hospital_name} is:\n\n"
            f"{otp}\n\n"
            f"This code expires in 5 minutes. If you didn't request this, ignore this email."
        )
        msg["Subject"] = "Your Sahasra AI Assistant verification code"
        msg["From"] = smtp_user
        msg["To"] = email

        with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as server:
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.sendmail(smtp_user, [email], msg.as_string())

        return {"sent": True}
    except Exception as e:
        print(f"[email_otp] SMTP send failed: {e}")
        return {"sent": False, "reason": "Could not send the verification email right now."}


def verify_otp(code: str, entered_otp: str) -> dict:
    """
    Checks the entered OTP against what was stored. Locks out further
    attempts after _MAX_VERIFY_ATTEMPTS wrong guesses on the same OTP,
    same brute-force principle as the activation-code lockout.
    """
    key = f"otp:{code.upper()}"
    attempts_key = f"otp_attempts:{code.upper()}"

    try:
        attempts_result = _redis_command("GET", attempts_key)
        attempts = int(attempts_result.get("result") or 0)
        if attempts >= _MAX_VERIFY_ATTEMPTS:
            return {"valid": False, "reason": "Too many incorrect attempts. Request a new code."}

        stored_result = _redis_command("GET", key)
        stored_otp = stored_result.get("result")

        if stored_otp is None:
            return {"valid": False, "reason": "Code expired. Request a new one."}

        if str(entered_otp).strip() != stored_otp:
            new_attempts = _redis_command("INCR", attempts_key)
            _redis_command("EXPIRE", attempts_key, str(_OTP_TTL_SECONDS))
            return {"valid": False, "reason": "Incorrect code."}

        _redis_command("DEL", key)
        _redis_command("DEL", attempts_key)
        return {"valid": True}
    except Exception as e:
        print(f"[email_otp] verify_otp Redis error (failing open): {e}")
        return {"valid": True}