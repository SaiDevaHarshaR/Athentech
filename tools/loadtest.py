"""Load test for the chat API (no dependencies).  Example:
   python tools/loadtest.py --url https://api.athentech.in --code KLIS-ADMIN-75605 --users 30 --requests 4
Each simulated user asks real questions in a loop with its own device id. Reports speed (median / 95th percentile), errors and 429s.
Start small (10 users). Questions that need the AI cost tokens - use --question "how many bills yesterday" (quick report, no AI) for a pure server test."""
import argparse
import json
import statistics
import threading
import time
import urllib.error
import urllib.request

ap = argparse.ArgumentParser()
ap.add_argument("--url", required=True)
ap.add_argument("--code", required=True)
ap.add_argument("--users", type=int, default=10)
ap.add_argument("--requests", type=int, default=3)
ap.add_argument("--question", action="append", default=[])
ap.add_argument("--timeout", type=int, default=90)
ap.add_argument("--device", default="", help="use ONE device id for every user (the code may be locked to a single device - then use the id your own browser uses)")
a = ap.parse_args()
Q = a.question or ["how many bills yesterday", "collection today", "top doctors this month"]
lat, errs, codes, lock = [], [], {}, threading.Lock()


def user(i):
    for n in range(a.requests):
        body = json.dumps({"question": Q[(i + n) % len(Q)], "activation_code": a.code, "chat_history": [], "device_fingerprint": a.device or ("load-%d" % i)}).encode()
        req = urllib.request.Request(a.url.rstrip("/") + "/ask", data=body, headers={"Content-Type": "application/json"}, method="POST")
        t = time.time()
        try:
            with urllib.request.urlopen(req, timeout=a.timeout) as r:
                j = json.loads(r.read() or b"{}")
                st = r.status
                ok = j.get("status") == "success"
                why = str(j.get("answer") or j.get("message") or j.get("detail") or "")[:90].replace("\n", " ")
        except urllib.error.HTTPError as e:
            st, ok = e.code, False
            try:
                with lock: errs.append("HTTP %s: %s" % (e.code, str(json.loads(e.read() or b"{}").get("detail") or "")[:90]))
            except Exception:
                pass
        except Exception as e:
            st, ok = 0, False
            with lock: errs.append(type(e).__name__)
        d = time.time() - t
        with lock:
            codes[st] = codes.get(st, 0) + 1
            lat.append(d)
            if not ok and st == 200: errs.append("answer-error: " + why)


t0 = time.time()
ths = [threading.Thread(target=user, args=(i,)) for i in range(a.users)]
[t.start() for t in ths]; [t.join() for t in ths]
tot = time.time() - t0
lat.sort()
print("requests: %d in %.1fs (%.1f/s)" % (len(lat), tot, len(lat) / tot if tot else 0))
if lat:
    print("median %.2fs   95th percentile %.2fs   slowest %.2fs" % (statistics.median(lat), lat[min(len(lat) - 1, int(len(lat) * 0.95))], lat[-1]))
print("HTTP codes:", codes, "| problems:", {e: errs.count(e) for e in set(errs)} or "none")
print("429 = the rate limiter stepped in (raise SAHASRA_RATE_ASK if many users share one office IP).")
