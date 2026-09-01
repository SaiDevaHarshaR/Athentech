"""
Actually sends the "Email alerts" the Settings page has been promising.
Previously toggling email_alerts_enabled just persisted a flag with no
delivery mechanism behind it at all.

Uses Python's stdlib smtplib — no new dependency. Reads SMTP config from
the settings table (smtp_host, smtp_port, smtp_user, smtp_password,
alert_email_to), all configurable from the admin Settings page.
"""

import smtplib
from email.mime.text import MIMEText


def send_alert_email(subject: str, body: str) -> tuple[bool, str]:
    """
    Returns (success, message). Never raises — a misconfigured or down
    SMTP server should not crash whatever triggered the alert.
    """
    from auth.license_service import get_settings
    s = get_settings()

    if not s.get("email_alerts_enabled"):
        return False, "Email alerts are disabled in Settings."

    host = s.get("smtp_host")
    to_addr = s.get("alert_email_to")

    if not host or not to_addr:
        return False, "SMTP host and/or alert recipient email are not configured in Settings."

    port = int(s.get("smtp_port") or 587)
    user = s.get("smtp_user") or ""
    password = s.get("smtp_password") or ""

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = user or "sahasra-ai@localhost"
    msg["To"] = to_addr

    try:
        with smtplib.SMTP(host, port, timeout=10) as server:
            server.starttls()
            if user:
                server.login(user, password)
            server.sendmail(msg["From"], [to_addr], msg.as_string())
        return True, f"Email sent to {to_addr}"
    except Exception as e:
        return False, f"Failed to send email: {type(e).__name__}: {e}"
