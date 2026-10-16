"""Outbound email for scheduled reports. Uses the SMTP details already saved in Admin > Settings:
the 'Alert' mail account if set, otherwise the 'Verification email' account. No new dependency. Never raises."""
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


def _creds():
    try:
        from auth.license_service import get_settings
        s = get_settings()
        if s.get("alert_smtp_host") and s.get("alert_smtp_user"):
            return (s["alert_smtp_host"], int(s.get("alert_smtp_port") or 587), s["alert_smtp_user"], s.get("alert_smtp_password") or "")
    except Exception:
        pass
    try:
        from auth.admin_account import _smtp_settings
        h, p, u, pw = _smtp_settings()
        if h and u:
            return (h, p, u, pw)
    except Exception:
        pass
    return None


def configured() -> bool:
    return _creds() is not None


def send(to_list, subject, text, html=None):
    """-> (ok, detail)"""
    c = _creds()
    if not c:
        return False, "Email is not set up on this server (Admin > Settings > SMTP)."
    host, port, user, pwd = c
    to_list = [t for t in (to_list or []) if t]
    if not to_list:
        return False, "No email recipient."
    msg = MIMEMultipart("alternative")
    msg["Subject"], msg["From"], msg["To"] = subject, user, ", ".join(to_list)
    msg.attach(MIMEText(text, "plain", "utf-8"))
    if html:
        msg.attach(MIMEText(html, "html", "utf-8"))
    try:
        if port == 465:
            with smtplib.SMTP_SSL(host, port, timeout=15) as s:
                s.login(user, pwd); s.sendmail(user, to_list, msg.as_string())
        else:
            with smtplib.SMTP(host, port, timeout=15) as s:
                s.starttls(); s.login(user, pwd); s.sendmail(user, to_list, msg.as_string())
        return True, "sent to " + ", ".join(to_list)
    except Exception as e:
        return False, "email failed: " + type(e).__name__
