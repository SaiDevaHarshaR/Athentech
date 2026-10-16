"""B2B login codes over WhatsApp (Pinnacle) instead of Twilio.
Activate with  B2B_OTP_PROVIDER=pinnacle  (+ the PINNACLE_WA_* settings, and PINNACLE_WA_OTP_TEMPLATE_ID for an approved
authentication template). The code is generated here, stored only as a keyed hash (5 min, 5 tries, single use) in logs/b2b_otp.db.
It plugs into the existing B2B login flow by replacing auth.b2b_portal._twilio / _otp_delivery at startup - b2b_portal.py is not edited."""
import hashlib
import hmac
import os
import secrets
import sqlite3
import threading
import time

_LOCK = threading.Lock()
_DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs", "b2b_otp.db")
TTL, MAX_TRIES = 300, 5


def enabled():
    return os.environ.get("B2B_OTP_PROVIDER", "").strip().lower() == "pinnacle"


def _conn():
    os.makedirs(os.path.dirname(_DB), exist_ok=True)
    c = sqlite3.connect(_DB, timeout=10)
    c.execute("CREATE TABLE IF NOT EXISTS otp(phone TEXT PRIMARY KEY, h TEXT, exp REAL, tries INTEGER DEFAULT 0)")
    return c


def _key():
    k = os.environ.get("B2B_OTP_SECRET") or os.environ.get("SECRETS_ENCRYPTION_KEY") or os.environ.get("ENCRYPTION_KEY") or "sahasra-b2b-otp"
    return k.encode()


def _h(phone, code):
    return hmac.new(_key(), (phone + "|" + code).encode(), hashlib.sha256).hexdigest()


def start(phone):
    """-> {'status': 'pending'} when the WhatsApp message was accepted; raises RuntimeError(user-safe text) otherwise."""
    from notifications import whatsapp
    code = "%06d" % secrets.randbelow(1000000)
    with _LOCK:
        c = _conn()
        try:
            c.execute("REPLACE INTO otp(phone,h,exp,tries) VALUES(?,?,?,0)", (phone, _h(phone, code), time.time() + TTL))
            c.commit()
        finally:
            c.close()
    ok, detail = whatsapp.send_otp(phone, code)
    if not ok:
        print("[b2b-otp] WhatsApp send failed: %s" % str(detail)[:200], flush=True)
        raise RuntimeError("The verification message could not be sent. Please try again later or contact support.")
    return {"status": "pending"}


def check(phone, code):
    with _LOCK:
        c = _conn()
        try:
            r = c.execute("SELECT h,exp,tries FROM otp WHERE phone=?", (phone,)).fetchone()
            if not r:
                return {"status": "expired"}
            h, exp, tries = r
            if time.time() > exp or tries >= MAX_TRIES:
                c.execute("DELETE FROM otp WHERE phone=?", (phone,)); c.commit()
                return {"status": "expired"}
            if hmac.compare_digest(h, _h(phone, str(code))):
                c.execute("DELETE FROM otp WHERE phone=?", (phone,)); c.commit()      # single use
                return {"status": "approved"}
            c.execute("UPDATE otp SET tries=tries+1 WHERE phone=?", (phone,)); c.commit()
            return {"status": "denied"}
        finally:
            c.close()


def install():
    """Swap the Twilio calls of the B2B portal for the WhatsApp ones when B2B_OTP_PROVIDER=pinnacle."""
    if not enabled():
        return False
    from auth import b2b_portal as b
    from fastapi import HTTPException
    if getattr(b._twilio, "_pinnacle", False):
        return True

    def _twilio(path, form):
        phone = str(form.get("To") or "")
        if path == "Verifications":
            try:
                return start(phone)
            except RuntimeError as e:
                raise HTTPException(502, str(e))
        if path == "VerificationCheck":
            return check(phone, form.get("Code", ""))
        raise HTTPException(503, "Verification is not available.")
    _twilio._pinnacle = True
    b._twilio = _twilio
    _orig = b._otp_delivery
    b._otp_delivery = lambda: "twilio" if enabled() else _orig()      # "twilio" = the non-test branch, now served by WhatsApp
    return True
