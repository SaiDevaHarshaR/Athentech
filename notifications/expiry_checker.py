"""
Periodically checks for licenses expiring soon and fires real alerts
(email/webhook) — this is what the "Email alerts for expiring licenses"
setting actually does now, instead of just being a toggle with nothing
behind it.

Started once at app startup (see main.py) via start_background_expiry_checker().
Runs in a daemon thread with a plain time.sleep loop — no new scheduler
dependency (APScheduler/Celery) for what's currently a single check-once-
a-day job. Revisit if the alerting needs get more sophisticated than that.
"""

import threading
import time
from datetime import datetime, timedelta

from database.license_db import get_conn
from notifications.email import send_alert_email
from notifications.webhook import send_webhook_alert

_last_alert_date = None  # crude "once per day" guard, see check_and_alert()


def get_expiring_licenses(days_ahead: int = 7) -> list:
    conn = get_conn()
    today = datetime.utcnow().date()
    cutoff = (today + timedelta(days=days_ahead)).isoformat()
    today_str = today.isoformat()

    rows = conn.execute(
        "SELECT code, hospital_name, role, expiry_date FROM licenses "
        "WHERE status IN ('Active', 'Trial') AND expiry_date >= ? AND expiry_date <= ? "
        "ORDER BY expiry_date ASC",
        (today_str, cutoff)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def check_and_alert(days_ahead: int = 7) -> dict:
    """
    Checks for expiring licenses and sends one alert (email + webhook,
    whichever are configured/enabled) if any are found. Returns a summary
    dict — used by both the background loop and the manual test endpoint.
    """
    global _last_alert_date

    expiring = get_expiring_licenses(days_ahead)
    result = {"checked_at": datetime.utcnow().isoformat(), "expiring_count": len(expiring), "alerts_sent": []}

    if not expiring:
        return result

    today_str = datetime.utcnow().date().isoformat()
    if _last_alert_date == today_str:
        result["skipped"] = "Already alerted today (once-per-day guard)"
        return result

    lines = [f"{l['code']} ({l['hospital_name']}, {l['role']}) expires {l['expiry_date']}" for l in expiring]
    subject = f"Sahasra AI: {len(expiring)} license(s) expiring within {days_ahead} days"
    body = "\n".join(lines)

    email_ok, email_msg = send_alert_email(subject, body)
    result["alerts_sent"].append({"channel": "email", "success": email_ok, "message": email_msg})

    webhook_ok, webhook_msg = send_webhook_alert("licenses_expiring", {"count": len(expiring), "licenses": expiring})
    result["alerts_sent"].append({"channel": "webhook", "success": webhook_ok, "message": webhook_msg})

    if email_ok or webhook_ok:
        _last_alert_date = today_str

    return result


def _background_loop(interval_hours: float):
    while True:
        try:
            check_and_alert()
        except Exception as e:
            print(f"Expiry checker error (non-fatal): {e}")
        time.sleep(interval_hours * 60 * 60)


def start_background_expiry_checker(interval_hours: float = 24):
    thread = threading.Thread(target=_background_loop, args=(interval_hours,), daemon=True)
    thread.start()
    return thread
