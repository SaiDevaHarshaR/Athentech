"""Outside uptime watcher (stdlib only). Run it on ANY other machine (or a cheap VPS / office PC) - not on the Sahasra server.
   python tools/uptime_watch.py --url https://api.athentech.in/health --every 60 --fail-after 2
Emails you when the API is down (and again when it is back). Set these environment variables:
   UPTIME_SMTP_HOST, UPTIME_SMTP_PORT (587), UPTIME_SMTP_USER, UPTIME_SMTP_PASS, UPTIME_FROM, UPTIME_TO (comma separated)
Optional WhatsApp/SMS-style webhook: UPTIME_WEBHOOK (POSTs {"text": "..."}).  Windows: run it with Task Scheduler "At startup"."""
import argparse
import json
import os
import smtplib
import ssl
import time
import urllib.request
from email.message import EmailMessage

ap = argparse.ArgumentParser()
ap.add_argument("--url", required=True)
ap.add_argument("--every", type=int, default=60)
ap.add_argument("--fail-after", type=int, default=2, help="alert after this many failed checks in a row")
ap.add_argument("--timeout", type=int, default=15)
ap.add_argument("--slow", type=float, default=8.0, help="seconds; slower than this counts as a failure")
ap.add_argument("--once", action="store_true", help="check once and exit (code 1 if down) - for other schedulers")
a = ap.parse_args()


def check():
    t = time.time()
    try:
        with urllib.request.urlopen(urllib.request.Request(a.url, headers={"User-Agent": "sahasra-uptime"}), timeout=a.timeout) as r:
            body = r.read(2000).decode("utf-8", "ignore")
            d = time.time() - t
            if r.status != 200:
                return False, "HTTP %s" % r.status
            if d > a.slow:
                return False, "too slow (%.1fs)" % d
            return True, "ok %.2fs %s" % (d, body[:60].replace("\n", " "))
    except Exception as e:
        return False, type(e).__name__ + ": " + str(e)[:120]


def notify(subject, text):
    print("[%s] %s - %s" % (time.strftime("%Y-%m-%d %H:%M:%S"), subject, text), flush=True)
    host, to = os.getenv("UPTIME_SMTP_HOST"), [x.strip() for x in os.getenv("UPTIME_TO", "").split(",") if x.strip()]
    if host and to:
        try:
            m = EmailMessage()
            m["Subject"], m["From"], m["To"] = subject, os.getenv("UPTIME_FROM") or os.getenv("UPTIME_SMTP_USER"), ", ".join(to)
            m.set_content(text)
            with smtplib.SMTP(host, int(os.getenv("UPTIME_SMTP_PORT", "587")), timeout=20) as s:
                s.starttls(context=ssl.create_default_context())
                if os.getenv("UPTIME_SMTP_USER"):
                    s.login(os.getenv("UPTIME_SMTP_USER"), os.getenv("UPTIME_SMTP_PASS", ""))
                s.send_message(m)
        except Exception as e:
            print("email failed:", type(e).__name__, e, flush=True)
    hook = os.getenv("UPTIME_WEBHOOK")
    if hook:
        try:
            urllib.request.urlopen(urllib.request.Request(hook, data=json.dumps({"text": subject + " - " + text}).encode(), headers={"Content-Type": "application/json"}, method="POST"), timeout=15).read()
        except Exception as e:
            print("webhook failed:", type(e).__name__, flush=True)


if a.once:
    ok, why = check()
    print(("UP " if ok else "DOWN ") + why)
    raise SystemExit(0 if ok else 1)
fails, down_since = 0, None
while True:
    ok, why = check()
    if ok:
        if down_since:
            notify("Sahasra AI is back", "Back online after %d min. %s" % ((time.time() - down_since) // 60, why))
            down_since = None
        fails = 0
    else:
        fails += 1
        print("[%s] check failed (%d): %s" % (time.strftime("%H:%M:%S"), fails, why), flush=True)
        if fails >= a.fail_after and not down_since:
            down_since = time.time()
            notify("Sahasra AI is DOWN", "%s failed %d times in a row. Last error: %s" % (a.url, fails, why))
    time.sleep(a.every)
