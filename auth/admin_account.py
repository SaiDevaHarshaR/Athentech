"""Admin account self-service: forgot password (email / SMS code), change username/password, recovery contacts,
'remember me' sessions and login throttling. One module shared by the Admin panel, Guardian and Answer Review.

All three websites use the same admin accounts (admins table), so one set of endpoints serves them all.
Secrets are never logged or returned. Reset codes are stored only as salted hashes, expire in 10 minutes and allow 5 tries.
"""
from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import smtplib
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from email.mime.text import MIMEText

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from auth.admin_auth import require_admin, create_admin_token
from auth.pwhash import hash_password, verify_password, is_legacy

router = APIRouter()
REMEMBER_TTL = 3650 * 24 * 3600     # 'keep me signed in': effectively until sign-out / cleared browser / password change
RESET_TTL_MIN = 10
MAX_CODE_TRIES = 5
_USERNAME = re.compile(r"^[A-Za-z0-9._@-]{3,60}$")      # no ':' (tokens use it as a separator)
_PHONE = re.compile(r"^\+\d{8,15}$")
_EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,200}\.[^@\s]{2,}$")
_lock = threading.Lock()
_hits: dict = {}
_schema_ok = False
_PW_CACHE: dict = {}


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _iso(dt):
    return dt.isoformat(timespec="seconds")


# --------------------------------------------------------------------------- throttling (per process)
def _throttle(key: str, limit: int, window: int) -> bool:
    """True if allowed. Records the hit."""
    now = time.time()
    with _lock:
        arr = [t for t in _hits.get(key, []) if now - t < window]
        if len(arr) >= limit:
            _hits[key] = arr
            return False
        arr.append(now)
        _hits[key] = arr
        if len(_hits) > 5000:
            for k in list(_hits)[:1000]:
                _hits.pop(k, None)
    return True


def _failed_count(key: str, window: int) -> int:
    now = time.time()
    with _lock:
        return len([t for t in _hits.get(key, []) if now - t < window])


def login_guard(ip: str, username: str):
    """Raise 429 after 8 failed sign-ins in 15 minutes for the same ip+username (or 30 per ip)."""
    if _failed_count(f"lf:{ip}:{username.lower()}", 900) >= 8 or _failed_count(f"lfi:{ip}", 900) >= 30:
        raise HTTPException(status_code=429, detail="Too many failed sign-ins. Wait 15 minutes or use 'Forgot password'.")


def login_failed(ip: str, username: str):
    _throttle(f"lf:{ip}:{username.lower()}", 10**6, 900)
    _throttle(f"lfi:{ip}", 10**6, 900)


# --------------------------------------------------------------------------- schema (portable, lazy)
def _conn():
    from database.license_db import get_conn
    return get_conn()


def _rollback(c):
    try:
        c._conn.rollback()
    except Exception:
        pass


def ensure_schema():
    global _schema_ok
    if _schema_ok:
        return
    c = _conn()
    try:
        for col, typ in (("email", "NVARCHAR(255)"), ("phone", "NVARCHAR(30)"), ("pw_changed_at", "NVARCHAR(40)")):
            try:
                c.execute(f"SELECT {col} FROM admins WHERE 1=0")
            except Exception:
                _rollback(c)
                c.execute(f"ALTER TABLE admins ADD {col} {typ}")
                c.commit()
        try:
            c.execute("SELECT id FROM admin_resets WHERE 1=0")
        except Exception:
            _rollback(c)
            c.execute("CREATE TABLE admin_resets (id NVARCHAR(40) PRIMARY KEY, username NVARCHAR(100) NOT NULL, "
                      "channel NVARCHAR(10) NOT NULL, salt NVARCHAR(40), code_hash NVARCHAR(100), expires_at NVARCHAR(40) NOT NULL, "
                      "attempts INT NOT NULL DEFAULT 0, used INT NOT NULL DEFAULT 0, created_at NVARCHAR(40) NOT NULL)")
            c.commit()
        _schema_ok = True
    finally:
        c.close()


def _admin(c, ident: str):
    """Active admin by username or by recovery email."""
    ident = (ident or "").strip()
    row = c.execute("SELECT id, username, display_name, status, email, phone, password_hash FROM admins WHERE username = ?",
                    (ident,)).fetchone()
    if not row and "@" in ident:
        row = c.execute("SELECT id, username, display_name, status, email, phone, password_hash FROM admins WHERE LOWER(email) = ?",
                        (ident.lower(),)).fetchone()
    if row and row["status"] != "Active":
        return None
    return row


def _mask_email(e):
    if not e or "@" not in e:
        return ""
    a, b = e.split("@", 1)
    return (a[:1] + "***" + a[-1:] if len(a) > 2 else a[:1] + "*") + "@" + b


def _mask_phone(p):
    return ("*" * (len(p) - 4) + p[-4:]) if p and len(p) > 4 else ""


def _check_policy(pw: str, username: str = ""):
    if len(pw) < 8:
        raise ValueError("Password must be at least 8 characters.")
    if not re.search(r"[A-Za-z]", pw) or not re.search(r"\d", pw):
        raise ValueError("Password needs at least one letter and one number.")
    if username and pw.lower() == username.lower():
        raise ValueError("Password cannot be the same as the username.")


def _set_password(c, username: str, new_pw: str):
    c.execute("UPDATE admins SET password_hash = ?, pw_changed_at = ? WHERE username = ?",
              (hash_password(new_pw), str(int(time.time())), username))
    c.commit()
    _PW_CACHE.pop(username, None)


def _audit(event: str, actor: str, detail: str = ""):
    try:
        from audit.log import audit
        audit(event=event, role=None, code=None, question=None, meta={"actor": actor, "detail": detail})
    except Exception:
        pass


# --------------------------------------------------------------------------- session invalidation
def token_still_valid(username: str, issued_at: int) -> bool:
    """Tokens issued before the last password change stop working. Cached 30s; fails open if the DB is unreachable."""
    try:
        hit = _PW_CACHE.get(username)
        if not hit or time.time() - hit[1] > 30:
            ensure_schema()
            c = _conn()
            try:
                r = c.execute("SELECT pw_changed_at, status FROM admins WHERE username = ?", (username,)).fetchone()
                n_admins = None if r else c.execute("SELECT COUNT(*) AS n FROM admins").fetchone()["n"]
            finally:
                c.close()
            val = int(r["pw_changed_at"]) if r and r["pw_changed_at"] else 0
            # account removed/renamed/deactivated -> its tokens stop working (unless the admins table is empty: bootstrap login)
            active = (r["status"] == "Active") if r else (n_admins == 0)
            _PW_CACHE[username] = (val, time.time(), active)
            hit = _PW_CACHE[username]
        return bool(hit[2]) and int(issued_at) >= hit[0]
    except Exception:
        return True


# --------------------------------------------------------------------------- delivery
def _smtp_settings():
    c = _conn()
    try:
        rows = c.execute("SELECT [key], value FROM settings").fetchall()
    finally:
        c.close()
    s = {r["key"]: r["value"] for r in rows}
    from auth.secrets_crypto import decrypt_secret
    return (s.get("otp_smtp_host", ""), int(s.get("otp_smtp_port", 587) or 587), s.get("otp_smtp_user", ""),
            decrypt_secret(s.get("otp_smtp_password", "")))


def _send_email(to: str, subject: str, text: str) -> bool:
    host, port, user, pwd = _smtp_settings()
    if not host or not user:
        raise HTTPException(status_code=503, detail="Email is not set up on this server yet (Admin > Settings > Verification Email SMTP).")
    msg = MIMEText(text)
    msg["Subject"], msg["From"], msg["To"] = subject, user, to
    try:
        if port == 465:
            with smtplib.SMTP_SSL(host, port, timeout=10) as s:
                s.login(user, pwd); s.sendmail(user, [to], msg.as_string())
        else:
            with smtplib.SMTP(host, port, timeout=10) as s:
                s.starttls(); s.login(user, pwd); s.sendmail(user, [to], msg.as_string())
        return True
    except Exception as e:
        print(f"[admin_account] email send failed: {type(e).__name__}")
        return False


def _twilio(path, form):
    from auth.b2b_portal import _twilio as tw      # same Twilio Verify setup as the B2B portal
    return tw(path, form)


# --------------------------------------------------------------------------- forgot password
def request_reset(identifier: str, channel: str, ip: str) -> dict:
    ensure_schema()
    generic = {"status": "success", "message": "If that account has a recovery %s on file, a code has been sent. It expires in %d minutes."
               % ("email" if channel == "email" else "mobile number", RESET_TTL_MIN)}
    if channel not in ("email", "sms"):
        raise HTTPException(status_code=400, detail="Choose email or mobile.")
    ident = (identifier or "").strip()
    if not ident or len(ident) > 120:
        raise HTTPException(status_code=400, detail="Enter your username or recovery email.")
    if not _throttle(f"rq:{ip}", 10, 3600) or not _throttle(f"rq:{ident.lower()}", 3, 3600):
        raise HTTPException(status_code=429, detail="Too many reset requests. Try again in an hour.")
    c = _conn()
    try:
        row = _admin(c, ident)
        if not row:
            return generic
        contact = row["email"] if channel == "email" else row["phone"]
        if not contact:
            return generic
        rid = uuid.uuid4().hex
        expires = _iso(_now() + timedelta(minutes=RESET_TTL_MIN))
        if channel == "email":
            code = f"{secrets.randbelow(10**6):06d}"
            salt = secrets.token_hex(8)
            h = hashlib.sha256((salt + code).encode()).hexdigest()
            c.execute("UPDATE admin_resets SET used = 1 WHERE username = ? AND used = 0", (row["username"],))
            c.execute("INSERT INTO admin_resets(id,username,channel,salt,code_hash,expires_at,attempts,used,created_at) VALUES(?,?,?,?,?,?,0,0,?)",
                      (rid, row["username"], "email", salt, h, expires, _iso(_now())))
            c.commit()
            ok = _send_email(contact, "Sahasra admin password reset code",
                             f"Your Sahasra password reset code is {code}\n\nIt expires in {RESET_TTL_MIN} minutes. "
                             "If you did not ask for this, ignore this email - your password has not changed.")
            if not ok:
                raise HTTPException(status_code=502, detail="Could not send the email right now. Try again shortly.")
        else:
            c.execute("UPDATE admin_resets SET used = 1 WHERE username = ? AND used = 0", (row["username"],))
            c.execute("INSERT INTO admin_resets(id,username,channel,salt,code_hash,expires_at,attempts,used,created_at) VALUES(?,?,?,?,?,?,0,0,?)",
                      (rid, row["username"], "sms", "", "", expires, _iso(_now())))
            c.commit()
            r = _twilio("Verifications", {"To": contact, "Channel": "sms"})
            if r.get("status") not in ("pending", "approved"):
                raise HTTPException(status_code=502, detail="Could not send the SMS right now.")
        _audit("admin_reset_requested", row["username"], channel)
        return generic
    finally:
        c.close()


def confirm_reset(identifier: str, code: str, new_password: str, channel: str, ip: str) -> dict:
    ensure_schema()
    bad = HTTPException(status_code=400, detail="Invalid or expired code.")
    if channel not in ("email", "sms") or not re.fullmatch(r"\d{4,10}", code or ""):
        raise bad
    if not _throttle(f"cf:{ip}", 20, 3600):
        raise HTTPException(status_code=429, detail="Too many attempts. Try again in an hour.")
    c = _conn()
    try:
        row = _admin(c, identifier)
        if not row:
            raise bad
        try:
            _check_policy(new_password, row["username"])
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        rs = c.execute("SELECT id, salt, code_hash, expires_at, attempts, used FROM admin_resets WHERE username = ? AND channel = ? "
                       "ORDER BY created_at DESC", (row["username"], channel)).fetchall()
        rs = [r for r in rs if not r["used"]]
        if not rs or rs[0]["expires_at"] < _iso(_now()) or rs[0]["attempts"] >= MAX_CODE_TRIES:
            raise bad
        r0 = rs[0]
        c.execute("UPDATE admin_resets SET attempts = attempts + 1 WHERE id = ?", (r0["id"],))
        c.commit()
        if channel == "email":
            good = hmac.compare_digest(hashlib.sha256((r0["salt"] + code).encode()).hexdigest(), r0["code_hash"])
        else:
            good = _twilio("VerificationCheck", {"To": row["phone"], "Code": code}).get("status") == "approved"
        if not good:
            raise bad
        c.execute("UPDATE admin_resets SET used = 1 WHERE username = ?", (row["username"],))
        c.commit()
        _set_password(c, row["username"], new_password)
        _audit("admin_password_reset", row["username"], channel)
        return {"status": "success", "message": "Password changed. Sign in with your new password."}
    finally:
        c.close()


# --------------------------------------------------------------------------- account (signed-in)
def _verify_current(c, username: str, password: str):
    row = c.execute("SELECT password_hash FROM admins WHERE username = ?", (username,)).fetchone()
    if not row or not verify_password(row["password_hash"], password or ""):
        raise HTTPException(status_code=403, detail="Current password is incorrect.")


def _norm_phone(p: str) -> str:
    p = re.sub(r"[\s-]", "", p or "")
    if re.fullmatch(r"\d{10}", p):
        p = "+91" + p
    return p


class ForgotRequest(BaseModel):
    identifier: str
    channel: str = "email"


class ForgotConfirm(BaseModel):
    identifier: str
    code: str
    new_password: str
    channel: str = "email"


class ChangePassword(BaseModel):
    current_password: str
    new_password: str


class ChangeUsername(BaseModel):
    current_password: str
    new_username: str


class Recovery(BaseModel):
    current_password: str
    email: str = ""
    phone: str = ""


def _ip(request: Request) -> str:
    return request.client.host if request and request.client else "unknown"


@router.post("/admin/forgot/request")
def api_forgot_request(req: ForgotRequest, request: Request):
    return request_reset(req.identifier, req.channel, _ip(request))


@router.post("/admin/forgot/confirm")
def api_forgot_confirm(req: ForgotConfirm, request: Request):
    return confirm_reset(req.identifier, req.code, req.new_password, req.channel, _ip(request))


@router.get("/admin/account")
def api_account(admin: str = Depends(require_admin)):
    ensure_schema()
    c = _conn()
    try:
        r = c.execute("SELECT username, display_name, email, phone FROM admins WHERE username = ?", (admin,)).fetchone()
    finally:
        c.close()
    if not r:
        raise HTTPException(status_code=404, detail="Account not found.")
    return {"status": "success", "username": r["username"], "display_name": r["display_name"],
            "email": r["email"] or "", "phone": r["phone"] or "",
            "email_masked": _mask_email(r["email"]), "phone_masked": _mask_phone(r["phone"])}


@router.post("/admin/account/password")
def api_account_password(req: ChangePassword, admin: str = Depends(require_admin)):
    ensure_schema()
    c = _conn()
    try:
        _verify_current(c, admin, req.current_password)
        try:
            _check_policy(req.new_password, admin)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        _set_password(c, admin, req.new_password)
    finally:
        c.close()
    _audit("admin_password_changed", admin)
    return {"status": "success", "token": create_admin_token(admin), "message": "Password changed. Other sessions were signed out."}


@router.post("/admin/account/signout-all")
def api_account_signout_all(admin: str = Depends(require_admin)):
    """Invalidate every session of this account (all devices, including this one)."""
    ensure_schema()
    c = _conn()
    try:
        c.execute("UPDATE admins SET pw_changed_at = ? WHERE username = ?", (str(int(time.time())), admin))
        c.commit()
        _PW_CACHE.pop(admin, None)
    finally:
        c.close()
    _audit("admin_signout_all", admin)
    return {"status": "success", "message": "Signed out everywhere."}


@router.post("/admin/account/username")
def api_account_username(req: ChangeUsername, admin: str = Depends(require_admin)):
    ensure_schema()
    new = (req.new_username or "").strip()
    if not _USERNAME.match(new):
        raise HTTPException(status_code=400, detail="Username: 3-60 characters, letters, numbers and . _ @ - only.")
    c = _conn()
    try:
        _verify_current(c, admin, req.current_password)
        if new.lower() != admin.lower() and c.execute("SELECT 1 FROM admins WHERE LOWER(username) = ?", (new.lower(),)).fetchone():
            raise HTTPException(status_code=409, detail="That username is already taken.")
        c.execute("UPDATE admins SET username = ?, pw_changed_at = ? WHERE username = ?", (new, str(int(time.time())), admin))
        c.commit()
        _PW_CACHE.pop(admin, None)
    finally:
        c.close()
    _audit("admin_username_changed", admin, f"-> {new}")
    return {"status": "success", "username": new, "token": create_admin_token(new), "message": "Username changed."}


@router.post("/admin/account/recovery")
def api_account_recovery(req: Recovery, admin: str = Depends(require_admin)):
    ensure_schema()
    email = (req.email or "").strip()
    phone = _norm_phone(req.phone)
    if email and not _EMAIL.match(email):
        raise HTTPException(status_code=400, detail="That email address does not look right.")
    if phone and not _PHONE.match(phone):
        raise HTTPException(status_code=400, detail="Mobile number: include the country code, e.g. +919876543210.")
    c = _conn()
    try:
        _verify_current(c, admin, req.current_password)
        c.execute("UPDATE admins SET email = ?, phone = ? WHERE username = ?", (email or None, phone or None, admin))
        c.commit()
    finally:
        c.close()
    _audit("admin_recovery_updated", admin)
    return {"status": "success", "message": "Recovery details saved."}
