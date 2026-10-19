"""Send AthenTech demo/lead form — HTML email + unique request ID subject."""
from __future__ import annotations

import html
import json
import os
import random
import smtplib
import threading
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

_ID_LOCK = threading.Lock()


def _env(*keys: str, default: str = "") -> str:
    for k in keys:
        v = (os.getenv(k) or "").strip()
        if v:
            return v
    return default


def _id_store_path() -> Path:
    """Persist used demo IDs next to the process working directory."""
    base = Path(os.getenv("SAHASRA_DATA_DIR") or os.getcwd())
    return base / "data" / "demo_request_ids.json"


def allocate_unique_request_id() -> str:
    """
    Format: YYYYMMDD + 2 digits  (e.g. 2026101947)
    Guaranteed unique via on-disk set; if a day exhausts 00-99, uses 3+ digits.
    """
    prefix = datetime.now().strftime("%Y%m%d")
    path = _id_store_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    with _ID_LOCK:
        used = set()
        if path.exists():
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(raw, list):
                    used = set(str(x) for x in raw)
                elif isinstance(raw, dict) and isinstance(raw.get("ids"), list):
                    used = set(str(x) for x in raw["ids"])
            except Exception:
                used = set()

        # Prefer 2-digit random among free slots for today
        candidates = [f"{prefix}{i:02d}" for i in range(100) if f"{prefix}{i:02d}" not in used]
        if candidates:
            rid = random.choice(candidates)
        else:
            # Day full of 2-digit IDs — extend width so we never collide
            n = 100
            while True:
                rid = f"{prefix}{n:03d}"
                if rid not in used:
                    break
                n += 1

        used.add(rid)
        # Keep file from growing forever: retain last ~5000 + all of today
        today = [x for x in used if x.startswith(prefix)]
        older = sorted(x for x in used if not x.startswith(prefix))[-4000:]
        path.write_text(json.dumps({"ids": older + today}, indent=0), encoding="utf-8")
        return rid


def _smtp_config():
    from auth.license_service import get_settings
    s = get_settings()
    host = _env("DEMO_SMTP_HOST", "ALERT_SMTP_HOST", "OTP_SMTP_HOST") or (s.get("alert_smtp_host") or s.get("otp_smtp_host") or "").strip()
    port = int(_env("DEMO_SMTP_PORT", "ALERT_SMTP_PORT", "OTP_SMTP_PORT") or str(s.get("alert_smtp_port") or s.get("otp_smtp_port") or 587) or 587)
    user = _env("DEMO_SMTP_USER", "ALERT_SMTP_USER", "OTP_SMTP_USER") or (s.get("alert_smtp_user") or s.get("otp_smtp_user") or "").strip()
    password = _env("DEMO_SMTP_PASSWORD", "ALERT_SMTP_PASSWORD", "OTP_SMTP_PASSWORD") or (s.get("alert_smtp_password") or s.get("otp_smtp_password") or "").strip()
    to_addr = _env("DEMO_REQUEST_EMAIL", "ALERT_EMAIL_TO") or (s.get("alert_email_to") or user or "").strip()
    cc_list = [x for x in (_env("DEMO_REQUEST_CC1"), _env("DEMO_REQUEST_CC2")) if x]
    return host, port, user, password, to_addr, cc_list


def _build_html(payload: dict, kind: str, request_id: str) -> str:
    name = html.escape((payload.get("name") or "").strip())
    email = html.escape((payload.get("email") or "").strip())
    phone = html.escape((payload.get("phone") or "").strip())
    org = html.escape((payload.get("organization") or "").strip() or "—")
    reqs = html.escape((payload.get("requirements") or "").strip()).replace("\n", "<br/>")
    title = "Demo request" if kind == "demo" else "Chat lead details"
    badge = "DEMO" if kind == "demo" else "LEAD"
    rid = html.escape(request_id)

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"/><meta name="viewport" content="width=device-width"/></head>
<body style="margin:0;padding:0;background:#f1f5f9;font-family:Segoe UI,Helvetica Neue,Arial,sans-serif;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#f1f5f9;padding:28px 12px;">
    <tr><td align="center">
      <table role="presentation" width="560" cellspacing="0" cellpadding="0" style="max-width:560px;width:100%;background:#ffffff;border-radius:16px;overflow:hidden;box-shadow:0 12px 40px rgba(15,23,42,.08);">
        <tr>
          <td style="background:linear-gradient(135deg,#0b1f3a 0%,#1e3a5f 100%);padding:14px 24px;color:#94a3b8;font-size:12px;">
            <span style="color:#fdba74;font-weight:700;">ATHENTECH</span>
            &nbsp;·&nbsp; Sahasra healthcare platform
            &nbsp;·&nbsp; <span style="color:#fff;font-weight:700;">#{rid}</span>
          </td>
        </tr>
        <tr>
          <td style="background:linear-gradient(135deg,#f97316 0%,#ea580c 100%);padding:22px 24px;">
            <div style="display:inline-block;background:rgba(255,255,255,.2);color:#fff;font-size:11px;font-weight:700;letter-spacing:1px;padding:4px 10px;border-radius:999px;margin-bottom:10px;">{badge} · #{rid}</div>
            <h1 style="margin:0;color:#ffffff;font-size:22px;font-weight:700;letter-spacing:-0.3px;">{title}</h1>
            <p style="margin:8px 0 0;color:#ffedd5;font-size:13px;line-height:1.45;">Submitted from the AthenTech Assistant chat widget on athentech.co.in</p>
          </td>
        </tr>
        <tr>
          <td style="padding:24px;">
            <p style="margin:0 0 16px;color:#64748b;font-size:13px;line-height:1.5;">Request ID <strong style="color:#0f172a;">#{rid}</strong> — reply directly to this email to contact the visitor.</p>
            <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="border:1px solid #e2e8f0;border-radius:12px;overflow:hidden;">
              <tr>
                <td style="padding:12px 16px;background:#fff7ed;border-bottom:1px solid #fed7aa;width:34%;color:#9a3412;font-size:12px;font-weight:700;">Request ID</td>
                <td style="padding:12px 16px;border-bottom:1px solid #e2e8f0;color:#0f172a;font-size:14px;font-weight:700;">#{rid}</td>
              </tr>
              <tr>
                <td style="padding:12px 16px;background:#fff7ed;border-bottom:1px solid #fed7aa;color:#9a3412;font-size:12px;font-weight:700;">Name</td>
                <td style="padding:12px 16px;border-bottom:1px solid #e2e8f0;color:#0f172a;font-size:14px;font-weight:600;">{name}</td>
              </tr>
              <tr>
                <td style="padding:12px 16px;background:#fff7ed;border-bottom:1px solid #fed7aa;color:#9a3412;font-size:12px;font-weight:700;">Email</td>
                <td style="padding:12px 16px;border-bottom:1px solid #e2e8f0;font-size:14px;"><a href="mailto:{email}" style="color:#ea580c;font-weight:600;text-decoration:none;">{email}</a></td>
              </tr>
              <tr>
                <td style="padding:12px 16px;background:#fff7ed;border-bottom:1px solid #fed7aa;color:#9a3412;font-size:12px;font-weight:700;">Phone</td>
                <td style="padding:12px 16px;border-bottom:1px solid #e2e8f0;font-size:14px;"><a href="tel:{phone}" style="color:#0f172a;font-weight:600;text-decoration:none;">{phone}</a></td>
              </tr>
              <tr>
                <td style="padding:12px 16px;background:#fff7ed;border-bottom:1px solid #fed7aa;color:#9a3412;font-size:12px;font-weight:700;">Organization</td>
                <td style="padding:12px 16px;border-bottom:1px solid #e2e8f0;color:#0f172a;font-size:14px;">{org}</td>
              </tr>
              <tr>
                <td style="padding:12px 16px;background:#fff7ed;vertical-align:top;color:#9a3412;font-size:12px;font-weight:700;">Requirements</td>
                <td style="padding:12px 16px;color:#1e293b;font-size:14px;line-height:1.55;">{reqs}</td>
              </tr>
            </table>
            <table role="presentation" cellspacing="0" cellpadding="0" style="margin-top:22px;">
              <tr>
                <td style="background:linear-gradient(135deg,#f97316,#ea580c);border-radius:10px;">
                  <a href="mailto:{email}?subject=Re%3A%20Demo%20-Request%20%23{rid}" style="display:inline-block;padding:12px 20px;color:#ffffff;font-size:13px;font-weight:700;text-decoration:none;">Reply to {name}</a>
                </td>
              </tr>
            </table>
          </td>
        </tr>
        <tr>
          <td style="background:#0b1f3a;padding:16px 24px;color:#94a3b8;font-size:11px;line-height:1.5;">
            <strong style="color:#fdba74;">AthenTech</strong> · Hyderabad · Bangalore · Vijayawada · Vizag<br/>
            Sales +91 970 5480 699 · <a href="https://www.athentech.co.in/" style="color:#fdba74;text-decoration:none;">www.athentech.co.in</a>
          </td>
        </tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""


def _plain(payload: dict, request_id: str) -> str:
    return (
        f"Request ID: #{request_id}\n"
        f"Name: {payload.get('name','')}\n"
        f"Email: {payload.get('email','')}\n"
        f"Phone: {payload.get('phone','')}\n"
        f"Organization: {payload.get('organization') or '(not provided)'}\n"
        f"Requirements:\n{payload.get('requirements','')}\n"
    )


def send_demo_request(payload: dict, kind: str = "demo") -> tuple[bool, str]:
    host, port, user, password, to_addr, cc_list = _smtp_config()
    if not host:
        return False, "SMTP host not set. Add DEMO_SMTP_HOST in .env"
    if not to_addr:
        return False, "Add DEMO_REQUEST_EMAIL=... in .env"

    name = (payload.get("name") or "").strip()
    email = (payload.get("email") or "").strip()
    phone = (payload.get("phone") or "").strip()
    reqs = (payload.get("requirements") or "").strip()
    if not name or not email or not phone or not reqs:
        return False, "Name, email, phone and requirements are required."

    request_id = allocate_unique_request_id()
    # Subject: Demo -Request #{Unique ID}
    if kind == "demo":
        subject = f"Demo -Request #{request_id}"
    else:
        subject = f"Lead -Request #{request_id}"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = user or "noreply@athentech.co.in"
    msg["To"] = to_addr
    if cc_list:
        msg["Cc"] = ", ".join(cc_list)
    msg["Reply-To"] = email
    msg.attach(MIMEText(_plain(payload, request_id), "plain", "utf-8"))
    msg.attach(MIMEText(_build_html(payload, kind=kind, request_id=request_id), "html", "utf-8"))

    recipients = [to_addr] + cc_list
    try:
        with smtplib.SMTP(host, port, timeout=20) as server:
            server.starttls()
            if user:
                server.login(user, password)
            server.sendmail(msg["From"], recipients, msg.as_string())
        return True, f"Sent to {to_addr} id=#{request_id}" + (f" (cc: {', '.join(cc_list)})" if cc_list else "")
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"
