"""Scheduled collection reports: "send this client's collection summary to these people, on this basis, at this time".

How it works
  * A schedule = client + channels (email / WhatsApp / both) + recipients + collections included + basis (daily / weekly /
    monthly) + send time. Stored in logs/report_schedules.db (no admin-DB migration needed).
  * The scheduler thread (scheduler.runner) calls tick() every minute. A due schedule is CLAIMED first (next_run moved on in
    one atomic UPDATE), so it is sent exactly once, and a long outage never floods people with stale reports (>6h late = skipped).
  * The report text is produced by the SAME verified agent used by the chatbot (client's own database, client's own AI key,
    number guard), so it works for every client schema without per-client code.
  * Basis -> period:  daily   = yesterday
                      weekly  = the 7 days ending yesterday   (sent on the chosen weekday)
                      monthly = the previous calendar month   (sent on the chosen day of month, 1-28)
Times are in the report time zone (default India, UTC+5:30; SAHASRA_REPORT_TZ_MINUTES to change).
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import threading
import time
from datetime import date, datetime, timedelta, timezone

_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
_DB = os.environ.get("SAHASRA_REPORT_DB") or os.path.join(_DIR, "report_schedules.db")
TZ_MIN = int(os.environ.get("SAHASRA_REPORT_TZ_MINUTES", "330") or 330)
STALE_S = 6 * 3600
_LOCK = threading.Lock()
_RUN_LOCK = threading.Lock()

SECTIONS = {
    "total": ("Total collection, bills & average bill", "the total collection (gross revenue), the number of bills and the average bill value"),
    "mode": ("Payment-mode split", "the collection split by payment mode (cash, card, UPI, cheque, etc.)"),
    "branch": ("Branch-wise collection", "the collection by branch / centre"),
    "tests": ("Top tests by revenue", "the top 5 tests (investigations) by revenue"),
    "doctors": ("Top referring doctors", "the top 5 referring doctors by revenue"),
    "dues": ("Outstanding / pending dues", "outstanding or pending dues, if the data has them"),
}
FREQUENCIES = ("daily", "weekly", "monthly")
CHANNELS = ("email", "whatsapp")
_EMAIL_RX = re.compile(r"^[^@\s,;]+@[^@\s,;]+\.[^@\s,;]{2,}$")
_PHONE_RX = re.compile(r"^\+[1-9]\d{7,14}$")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS schedules(
  id INTEGER PRIMARY KEY AUTOINCREMENT, client TEXT NOT NULL, hospital TEXT, channels TEXT NOT NULL,
  email_to TEXT DEFAULT '', whatsapp_to TEXT DEFAULT '', frequency TEXT NOT NULL, send_time TEXT NOT NULL,
  weekday INTEGER DEFAULT 0, month_day INTEGER DEFAULT 1, sections TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 1,
  next_run_ts REAL, last_run_ts REAL, last_status TEXT, last_detail TEXT, created_by TEXT, created_ts REAL);
CREATE TABLE IF NOT EXISTS runs(
  id INTEGER PRIMARY KEY AUTOINCREMENT, schedule_id INTEGER, ts REAL, status TEXT, detail TEXT, manual INTEGER DEFAULT 0);
"""


# ----------------------------------------------------------------------------- storage
def _conn():
    os.makedirs(os.path.dirname(_DB), exist_ok=True)
    c = sqlite3.connect(_DB, timeout=8)
    c.row_factory = sqlite3.Row
    c.executescript(_SCHEMA)
    return c


def _local_now(ts=None):
    return datetime.fromtimestamp(ts if ts is not None else time.time(), tz=timezone.utc).replace(tzinfo=None) + timedelta(minutes=TZ_MIN)


def _to_ts(local_dt: datetime) -> float:
    return (local_dt - timedelta(minutes=TZ_MIN)).replace(tzinfo=timezone.utc).timestamp()


def _row(r):
    d = dict(r)
    d["channels"] = [c for c in (d.get("channels") or "").split(",") if c]
    d["sections"] = [s for s in (d.get("sections") or "").split(",") if s]
    d["email_to"] = [e for e in (d.get("email_to") or "").split(",") if e]
    d["whatsapp_to"] = [e for e in (d.get("whatsapp_to") or "").split(",") if e]
    d["enabled"] = bool(d.get("enabled"))
    d["basis_text"] = basis_text(d)
    return d


def basis_text(s):
    t = s.get("send_time") or "08:00"
    f = s.get("frequency")
    if f == "daily":
        return "Every day at %s - covers yesterday" % t
    if f == "weekly":
        return "Every %s at %s - covers the previous 7 days" % (["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"][int(s.get("weekday") or 0) % 7], t)
    return "On day %s of every month at %s - covers the previous month" % (int(s.get("month_day") or 1), t)


# ----------------------------------------------------------------------------- time maths
def period_for(freq, today_local: date):
    """(from_date, to_date, label)"""
    if freq == "weekly":
        d2 = today_local - timedelta(days=1)
        return d2 - timedelta(days=6), d2, "the last 7 days"
    if freq == "monthly":
        first_this = today_local.replace(day=1)
        d2 = first_this - timedelta(days=1)
        return d2.replace(day=1), d2, d2.strftime("%B %Y")
    d = today_local - timedelta(days=1)
    return d, d, "yesterday (" + d.strftime("%d %b %Y") + ")"


def next_run_ts(freq, send_time, weekday=0, month_day=1, after_ts=None):
    """Next fire time (UTC epoch) strictly after `after_ts`."""
    now = _local_now(after_ts)
    hh, mm = [int(x) for x in send_time.split(":")]
    base = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if freq == "daily":
        cand = base if base > now else base + timedelta(days=1)
    elif freq == "weekly":
        cand = base + timedelta(days=(int(weekday) - base.weekday()) % 7)
        if cand <= now:
            cand += timedelta(days=7)
    else:
        md = max(1, min(28, int(month_day)))
        cand = base.replace(day=md)
        if cand <= now:
            y, m = (cand.year + 1, 1) if cand.month == 12 else (cand.year, cand.month + 1)
            cand = cand.replace(year=y, month=m, day=md)
    return _to_ts(cand)


# ----------------------------------------------------------------------------- validation + CRUD
def validate(d: dict, creating=True):
    """-> (clean dict, error). Everything the form can send is checked here; the UI is not trusted."""
    out, err = {}, None
    client = str(d.get("client") or "").strip().upper()
    if not client:
        return None, "Choose a client."
    out["client"] = client
    ch = [c for c in (d.get("channels") or []) if c in CHANNELS]
    if not ch:
        return None, "Choose Email, WhatsApp or both."
    out["channels"] = ",".join(dict.fromkeys(ch))
    emails = [e.strip() for e in re.split(r"[,;\s]+", ",".join(d.get("email_to") or []) if isinstance(d.get("email_to"), list) else str(d.get("email_to") or "")) if e.strip()]
    phones = [e.strip().replace(" ", "") for e in re.split(r"[,;\s]+", ",".join(d.get("whatsapp_to") or []) if isinstance(d.get("whatsapp_to"), list) else str(d.get("whatsapp_to") or "")) if e.strip()]
    if "email" in ch:
        if not emails:
            return None, "Enter at least one email address."
        bad = [e for e in emails if not _EMAIL_RX.match(e)]
        if bad:
            return None, "Not a valid email: " + bad[0]
    if "whatsapp" in ch:
        if not phones:
            return None, "Enter at least one WhatsApp number (with country code, e.g. +919876543210)."
        bad = [p for p in phones if not _PHONE_RX.match(p)]
        if bad:
            return None, "Not a valid WhatsApp number: %s (use +country code, digits only)" % bad[0]
    out["email_to"] = ",".join(emails[:10]) if "email" in ch else ""
    out["whatsapp_to"] = ",".join(phones[:10]) if "whatsapp" in ch else ""
    secs = [s for s in (d.get("sections") or []) if s in SECTIONS]
    if not secs:
        return None, "Tick at least one collection to include."
    out["sections"] = ",".join(dict.fromkeys(secs))
    f = str(d.get("frequency") or "").lower()
    if f not in FREQUENCIES:
        return None, "Choose daily, weekly or monthly."
    out["frequency"] = f
    st = str(d.get("send_time") or "08:00")
    if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", st):
        return None, "Send time must look like 08:00."
    out["send_time"] = st
    try:
        out["weekday"] = max(0, min(6, int(d.get("weekday") or 0)))
        out["month_day"] = max(1, min(28, int(d.get("month_day") or 1)))
    except (TypeError, ValueError):
        return None, "Invalid weekday / day of month."
    return out, None


def list_schedules():
    with _LOCK:
        c = _conn()
        try:
            return [_row(r) for r in c.execute("SELECT * FROM schedules ORDER BY id DESC").fetchall()]
        finally:
            c.close()


def get_schedule(sid):
    with _LOCK:
        c = _conn()
        try:
            r = c.execute("SELECT * FROM schedules WHERE id=?", (int(sid),)).fetchone()
            return _row(r) if r else None
        finally:
            c.close()


def save_schedule(clean: dict, hospital: str, actor: str, sid=None):
    nxt = next_run_ts(clean["frequency"], clean["send_time"], clean["weekday"], clean["month_day"])
    with _LOCK:
        c = _conn()
        try:
            if sid:
                c.execute("UPDATE schedules SET client=?,hospital=?,channels=?,email_to=?,whatsapp_to=?,frequency=?,send_time=?,"
                          "weekday=?,month_day=?,sections=?,next_run_ts=? WHERE id=?",
                          (clean["client"], hospital, clean["channels"], clean["email_to"], clean["whatsapp_to"], clean["frequency"],
                           clean["send_time"], clean["weekday"], clean["month_day"], clean["sections"], nxt, int(sid)))
            else:
                cur = c.execute("INSERT INTO schedules(client,hospital,channels,email_to,whatsapp_to,frequency,send_time,weekday,month_day,"
                                "sections,enabled,next_run_ts,created_by,created_ts) VALUES(?,?,?,?,?,?,?,?,?,?,1,?,?,?)",
                                (clean["client"], hospital, clean["channels"], clean["email_to"], clean["whatsapp_to"], clean["frequency"],
                                 clean["send_time"], clean["weekday"], clean["month_day"], clean["sections"], nxt, actor, time.time()))
                sid = cur.lastrowid
            c.commit()
        finally:
            c.close()
    return get_schedule(sid)


def set_enabled(sid, enabled):
    s = get_schedule(sid)
    if not s:
        return None
    nxt = next_run_ts(s["frequency"], s["send_time"], s["weekday"], s["month_day"]) if enabled else None
    with _LOCK:
        c = _conn()
        try:
            c.execute("UPDATE schedules SET enabled=?, next_run_ts=? WHERE id=?", (1 if enabled else 0, nxt, int(sid)))
            c.commit()
        finally:
            c.close()
    return get_schedule(sid)


def delete_schedule(sid):
    with _LOCK:
        c = _conn()
        try:
            c.execute("DELETE FROM schedules WHERE id=?", (int(sid),))
            c.execute("DELETE FROM runs WHERE schedule_id=?", (int(sid),))
            c.commit()
        finally:
            c.close()


def recent_runs(sid, limit=8):
    with _LOCK:
        c = _conn()
        try:
            return [dict(r) for r in c.execute("SELECT * FROM runs WHERE schedule_id=? ORDER BY id DESC LIMIT ?", (int(sid), limit)).fetchall()]
        finally:
            c.close()


def _record(sid, ok, detail, manual):
    with _LOCK:
        c = _conn()
        try:
            c.execute("INSERT INTO runs(schedule_id,ts,status,detail,manual) VALUES(?,?,?,?,?)", (int(sid), time.time(), "sent" if ok else "failed", detail[:400], 1 if manual else 0))
            c.execute("UPDATE schedules SET last_run_ts=?,last_status=?,last_detail=? WHERE id=?", (time.time(), "sent" if ok else "failed", detail[:400], int(sid)))
            c.execute("DELETE FROM runs WHERE id NOT IN (SELECT id FROM runs ORDER BY id DESC LIMIT 400)")
            c.commit()
        finally:
            c.close()


# ----------------------------------------------------------------------------- building the report text
_FENCE = re.compile(r"```(?:dashboard-card|json)?\s*(\{.*?\})\s*```", re.S)


def _card_lines(card: dict):
    L = []
    if card.get("title"):
        L.append(str(card["title"]))
    if card.get("subtitle"):
        L.append(str(card["subtitle"]))
    for m in card.get("meta") or []:
        if isinstance(m, dict) and m.get("text"):
            L.append(str(m["text"]))
    stats = card.get("stats") or []
    if stats:
        L.append("")
    for s in stats:
        if isinstance(s, dict) and s.get("label"):
            L.append("%s: %s" % (s["label"], s.get("value", "")))
    for k, v in card.items():
        if isinstance(v, dict) and isinstance(v.get("rows"), list):
            L.append("")
            L.append(str(v.get("title") or k) + (" " + str(v["subtitle"]) if v.get("subtitle") else ""))
            for r in v["rows"][:12]:
                if isinstance(r, dict):
                    L.append("  - %s: %s" % (r.get("label", ""), r.get("extra") or r.get("value", "")))
    return L


def to_plain_text(answer: str) -> str:
    """Turn a chatbot answer (maybe with a dashboard-card block / markdown) into clean text for email / WhatsApp."""
    text = str(answer or "")

    def rep(m):
        try:
            return "\n".join(_card_lines(json.loads(m.group(1))))
        except Exception:
            return ""
    text = _FENCE.sub(rep, text)
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"^#{1,6}\s*", "", text, flags=re.M)
    text = re.sub(r"[ \t]+\n", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def build_question(s, d1: date, d2: date, label: str) -> str:
    items = [SECTIONS[k][1] for k in s["sections"] if k in SECTIONS]
    rng = d1.strftime("%d %b %Y") if d1 == d2 else "%s to %s" % (d1.strftime("%d %b %Y"), d2.strftime("%d %b %Y"))
    return ("Collection report for %s (%s). Include only: %s. Use exactly the dates %s to %s. "
            "Reply as a short plain-text summary with exact figures from the database - no dashboard card, no tables, no follow-up questions."
            % (label, rng, "; ".join(items), d1.isoformat(), d2.isoformat()))


def generate(s):
    """-> (title, plain_text, tokens). Raises RuntimeError with a human message on failure."""
    from agent import heal, confidence as conf, answer_guard as ag
    creds = heal._client_creds(s["client"])
    if not creds:
        raise RuntimeError("This client's database details could not be found.")
    d1, d2, label = period_for(s["frequency"], _local_now().date())
    q = build_question(s, d1, d2, label)
    from agent.agent import ask_agent
    conf.begin(q)

    def once(qq):
        return ask_agent(qq, creds["db_name"], [], True, "admin", creds["hospital_name"], creds["db_server"],
                         creds["db_user"], creds["db_password"], s["client"], creds["institution_type"])
    ans, tok = once(q)
    ans, tok, info = ag.guard_numbers(once, q, ans, tok, conf)
    low = (ans or "").lower()
    if not (ans or "").strip() or any(b in low for b in ("couldn't get a reliable answer", "can't verify this from", "is not configured for this institution", "rejected the saved api key", "no credits")):
        raise RuntimeError("The AI could not produce a verified report: " + (str(ans)[:140] or "empty answer"))
    try:
        from auth.usage_limiter import record_usage
        record_usage(s["client"], tok)
    except Exception:
        pass
    freq = {"daily": "Daily", "weekly": "Weekly", "monthly": "Monthly"}[s["frequency"]]
    title = "%s - %s collection report" % (creds["hospital_name"], freq)
    return title, to_plain_text(ans), label, tok


def _html(title, label, text):
    import html as h
    body = "<br>".join(h.escape(line) for line in text.split("\n"))
    return ("<div style=\"font-family:Segoe UI,Arial,sans-serif;max-width:640px;margin:auto;border:1px solid #e3e6ef;border-radius:14px;overflow:hidden\">"
            "<div style=\"background:linear-gradient(120deg,#6a5cf6,#22b8d6);color:#fff;padding:18px 22px\"><div style=\"font-size:12px;letter-spacing:.14em;opacity:.85\">SAHASRA AI - SCHEDULED REPORT</div>"
            "<div style=\"font-size:20px;font-weight:700;margin-top:4px\">%s</div><div style=\"opacity:.9;font-size:13px\">%s</div></div>"
            "<div style=\"padding:20px 22px;font-size:14px;line-height:1.65;color:#222\">%s</div>"
            "<div style=\"padding:12px 22px;background:#f6f7fb;font-size:11px;color:#778\">Figures are read directly from your Sahasra database by the AI Agent. "
            "To change or stop this report, contact your administrator.</div></div>") % (h.escape(title), h.escape(label), body)


# ----------------------------------------------------------------------------- running
def run_schedule(sid, manual=False, dry=False):
    """Generate (and, unless dry, deliver) one schedule. -> {'ok', 'detail', 'text'}"""
    s = get_schedule(sid)
    if not s:
        return {"ok": False, "detail": "Schedule not found.", "text": ""}
    from notifications import mailer, whatsapp
    try:
        title, text, label, _tok = generate(s)
    except Exception as e:
        msg = str(e)[:300]
        if not dry:
            _record(sid, False, msg, manual)
            _ops(False)
        return {"ok": False, "detail": msg, "text": ""}
    if dry:
        return {"ok": True, "detail": "Preview only - nothing was sent.", "text": title + "\n" + label + "\n\n" + text}
    parts, ok_all = [], True
    if "email" in s["channels"]:
        ok, det = mailer.send(s["email_to"], "%s - %s" % (title, label), title + "\n" + label + "\n\n" + text, _html(title, label, text))
        parts.append("Email: " + det); ok_all &= ok
    if "whatsapp" in s["channels"]:
        ok, det = whatsapp.send(s["whatsapp_to"], label + "\n\n" + text, title)
        parts.append("WhatsApp: " + det); ok_all &= ok
    detail = " | ".join(parts)
    _record(sid, ok_all, detail, manual)
    _ops(ok_all)
    return {"ok": ok_all, "detail": detail, "text": text}


def _ops(ok):
    try:
        from observability.ops_lite import record_event
        record_event("scheduled_report", "success" if ok else "failure")
    except Exception:
        pass


def tick(now_ts=None):
    """Called every minute by the scheduler thread. Claims each due schedule atomically, then runs them one after another."""
    now = now_ts if now_ts is not None else time.time()
    claimed = []
    with _LOCK:
        c = _conn()
        try:
            due = c.execute("SELECT * FROM schedules WHERE enabled=1 AND next_run_ts IS NOT NULL AND next_run_ts<=?", (now,)).fetchall()
            for r in due:
                s = _row(r)
                nxt = next_run_ts(s["frequency"], s["send_time"], s["weekday"], s["month_day"], after_ts=now)
                cur = c.execute("UPDATE schedules SET next_run_ts=? WHERE id=? AND next_run_ts=?", (nxt, s["id"], r["next_run_ts"]))
                if cur.rowcount == 1:
                    if now - r["next_run_ts"] <= STALE_S:
                        claimed.append(s["id"])
                    else:
                        c.execute("INSERT INTO runs(schedule_id,ts,status,detail) VALUES(?,?,?,?)", (s["id"], now, "skipped", "Server was off at the send time; skipped to avoid sending a stale report."))
            c.commit()
        finally:
            c.close()
    if not claimed:
        return []

    def _worker():
        with _RUN_LOCK:
            for sid in claimed:
                try:
                    run_schedule(sid)
                except Exception as e:
                    _record(sid, False, "unexpected error: " + type(e).__name__, False)
                    _ops(False)
    threading.Thread(target=_worker, daemon=True, name="scheduled-reports").start()
    return claimed
