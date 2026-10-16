"""Ops alerts - turns the in-process counters into "something is wrong" messages, with no extra software.
Checked once a minute by the scheduler over a sliding ~10 minute window; each rule re-alerts at most every 30 minutes.
Delivery: the Alert email settings already in Admin > Settings (Email alerts enabled + recipient). Every alert is also
kept in memory and shown in Guardian > Live health > Recent alerts. Never raises."""
import os
import threading
import time
from collections import deque

WINDOW_S = int(os.getenv("SAHASRA_ALERT_WINDOW_SECONDS", "600"))
COOLDOWN_S = int(os.getenv("SAHASRA_ALERT_COOLDOWN_SECONDS", "1800"))
ENABLED = os.getenv("SAHASRA_ALERTS", "1") != "0"
_LOCK = threading.Lock()
_SAMPLES = deque(maxlen=200)          # (ts, requests, 5xx, {(kind,result): n})
_LAST = {}
_RECENT = deque(maxlen=50)


def recent():
    with _LOCK:
        return list(_RECENT)


def _counts(snap):
    ev = {(e["kind"], e["result"]): e["count"] for e in snap.get("backend_events", [])}
    return (time.time(), snap.get("http_requests", 0), snap.get("http_5xx", 0), ev)


def _fire(rule, detail):
    now = time.time()
    with _LOCK:
        if now - _LAST.get(rule, 0) < COOLDOWN_S:
            return False
        _LAST[rule] = now
        _RECENT.appendleft({"time": time.strftime("%Y-%m-%d %H:%M:%S"), "rule": rule, "detail": detail})
    try:
        from observability.ops_lite import record_event
        record_event("alert", "failure")
    except Exception:
        pass
    try:
        from notifications.email import send_alert_email
        send_alert_email("[Sahasra AI] " + rule, detail + "\n\n(Sent by the Sahasra AI Agent monitor. Details: Guardian > Live health.)")
    except Exception:
        pass
    return True


def evaluate(snap=None):
    """One evaluation pass. Returns the list of rules that fired (for tests)."""
    if not ENABLED:
        return []
    fired = []
    try:
        if snap is None:
            from observability.ops_lite import snapshot
            snap = snapshot()
        cur = _counts(snap)
        with _LOCK:
            _SAMPLES.append(cur)
            old = next((s for s in _SAMPLES if cur[0] - s[0] <= WINDOW_S), _SAMPLES[0])
        if cur[0] - old[0] < 60:
            return fired
        d_req, d_5xx = cur[1] - old[1], cur[2] - old[2]

        def dv(k, r):
            return cur[3].get((k, r), 0) - old[3].get((k, r), 0)
        mins = max(1, int((cur[0] - old[0]) / 60))
        if d_req >= 20 and d_5xx / d_req >= 0.10:
            fired.append(("Server errors rising", "%d of the last %d requests (%d%%) failed with a server error in ~%d min." % (d_5xx, d_req, 100 * d_5xx // d_req, mins)))
        if dv("ask", "failure") >= 3:
            fired.append(("Questions are failing", "%d questions crashed in ~%d min." % (dv("ask", "failure"), mins)))
        if dv("ai_provider", "failure") >= 3:
            fired.append(("AI provider problems", "%d answers could not be produced because a client's AI key/provider failed in ~%d min." % (dv("ai_provider", "failure"), mins)))
        p95 = snap.get("http_p95_seconds")
        if p95 and p95 > float(os.getenv("SAHASRA_ALERT_P95_SECONDS", "25")) and d_req >= 10:
            fired.append(("Service is slow", "The slowest 5%% of requests now take %.0f seconds." % p95))
        if dv("scheduled_report", "failure") >= 1:
            fired.append(("A scheduled report failed", "%d scheduled report(s) failed to send in ~%d min. See Settings > Scheduled Reports." % (dv("scheduled_report", "failure"), mins)))
        if dv("regression", "failure") >= 1:
            fired.append(("Regression test failed", "A saved question no longer passes. See Guardian > Heal > Regression tests."))
        return [r for r, d in fired if _fire(r, d)]
    except Exception:
        return fired
