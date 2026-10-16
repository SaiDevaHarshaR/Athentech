"""Admin extras (all additive, own SQLite file logs/admin_extras.db):
  * Accuracy checks   - nightly regression run on a schedule set in Settings (+ email on failure) and a CONSISTENCY test
                        (the same question asked several times must give the same figures)
  * Usage insights    - answer quality by hospital, most asked and most-failed questions
  * Backups & restore - consistent snapshots of Heal rules, scheduled reports, these settings and every white-label config
Routes are added by agent.guard_hooks at startup. Nothing here changes client data."""
import io
import json
import os
import re
import sqlite3
import threading
import time
import zipfile
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOGS = os.path.join(ROOT, "logs")
BACKUPS = os.path.join(ROOT, "backups")
_DB = os.path.join(LOGS, "admin_extras.db")
_LOCK = threading.Lock()
IST = timezone(timedelta(hours=5, minutes=30))
STATE = {"consistency": {"running": False, "done": 0, "total": 0}, "regression": {"running": False}}
SQLITE_FILES = ["heal.db", "report_schedules.db", "admin_extras.db"]
KEEP = 14


def _c():
    os.makedirs(LOGS, exist_ok=True)
    c = sqlite3.connect(_DB, timeout=10)
    c.row_factory = sqlite3.Row
    c.executescript("CREATE TABLE IF NOT EXISTS cfg(k TEXT PRIMARY KEY, v TEXT);"
                    "CREATE TABLE IF NOT EXISTS runs(id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT, ts TEXT, summary TEXT);")
    return c


def _now():
    return datetime.now(IST)


def get_cfg():
    d = {"nightly_enabled": False, "nightly_time": "02:30", "notify_email": "", "backup_enabled": True, "backup_time": "01:30"}
    with _LOCK:
        c = _c()
        try:
            for r in c.execute("SELECT k,v FROM cfg"):
                try:
                    d[r["k"]] = json.loads(r["v"])
                except Exception:
                    pass
        finally:
            c.close()
    return d


def set_cfg(patch):
    ok = {}
    if "nightly_enabled" in patch: ok["nightly_enabled"] = bool(patch["nightly_enabled"])
    if "backup_enabled" in patch: ok["backup_enabled"] = bool(patch["backup_enabled"])
    for k in ("nightly_time", "backup_time"):
        if k in patch:
            if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", str(patch[k])):
                raise ValueError("Time must look like 02:30 (24-hour).")
            ok[k] = str(patch[k])
    if "notify_email" in patch:
        em = [e.strip() for e in str(patch["notify_email"]).replace(";", ",").split(",") if e.strip()]
        if any(not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", e) for e in em) or len(em) > 5:
            raise ValueError("Enter up to 5 valid email addresses, separated by commas.")
        ok["notify_email"] = ", ".join(em)
    with _LOCK:
        c = _c()
        try:
            for k, v in ok.items():
                c.execute("REPLACE INTO cfg(k,v) VALUES(?,?)", (k, json.dumps(v)))
            c.commit()
        finally:
            c.close()
    return get_cfg()


def _save_run(kind, summary):
    with _LOCK:
        c = _c()
        try:
            c.execute("INSERT INTO runs(kind,ts,summary) VALUES(?,?,?)", (kind, _now().isoformat(timespec="seconds"), json.dumps(summary)))
            c.execute("DELETE FROM runs WHERE kind=? AND id NOT IN (SELECT id FROM runs WHERE kind=? ORDER BY id DESC LIMIT 20)", (kind, kind))
            c.commit()
        finally:
            c.close()


def last_run(kind):
    with _LOCK:
        c = _c()
        try:
            r = c.execute("SELECT ts,summary FROM runs WHERE kind=? ORDER BY id DESC LIMIT 1", (kind,)).fetchone()
        finally:
            c.close()
    if not r:
        return None
    d = json.loads(r["summary"])
    d["ts"] = r["ts"]
    return d


# ----------------------------------------------------------------------------- accuracy: regression (nightly / on demand)
def run_regression_bg(client=None, notify=True):
    if STATE["regression"]["running"]:
        return False
    STATE["regression"]["running"] = True

    def work():
        try:
            from agent import regression
            res = regression.run_all(client or None, limit=60)
            _save_run("regression", {**{k: res.get(k) for k in ("ran", "passed", "failed", "error")}, "results": (res.get("results") or [])[:60]})
            if notify and (res.get("failed") or res.get("error")):
                _notify("Sahasra accuracy check: %s question(s) failed" % (res.get("failed") or "?"),
                        "The nightly accuracy check re-asked every approved fix. %s of %s no longer pass.\n\nOpen Admin > Settings > Accuracy checks for details."
                        % (res.get("failed"), res.get("ran")))
        except Exception as e:
            _save_run("regression", {"error": str(e)[:200]})
        finally:
            STATE["regression"]["running"] = False
    threading.Thread(target=work, daemon=True, name="accuracy-run").start()
    return True


def _notify(subject, text):
    try:
        to = [e.strip() for e in get_cfg().get("notify_email", "").split(",") if e.strip()]
        if to:
            from notifications import mailer
            mailer.send(to, subject, text)
    except Exception:
        pass


# ----------------------------------------------------------------------------- accuracy: consistency
_NUM = re.compile(r"-?\d[\d,]*\.?\d*")


def _figures(text):
    out = set()
    for m in _NUM.findall(text or ""):
        try:
            v = float(m.replace(",", ""))
        except ValueError:
            continue
        if abs(v) >= 10:                       # ignore list numbers / tiny counts that are just wording
            out.add(round(v, 2))
    return out


def top_questions(client, n):
    from agent import answer_log
    since = (datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=30)).isoformat(timespec="seconds")
    with answer_log._LOCK:
        c = answer_log._conn()
        try:
            rows = c.execute("SELECT question, COUNT(*) n FROM answer_log WHERE UPPER(client)=UPPER(?) AND ts>=? AND source='llm' AND ok=1 "
                             "GROUP BY LOWER(question) ORDER BY n DESC LIMIT ?", (client, since, int(n))).fetchall()
        finally:
            c.close()
    return [r["question"] for r in rows if (r["question"] or "").strip()]


def run_consistency_bg(client, n=8, k=3):
    st = STATE["consistency"]
    if st["running"]:
        return False
    n, k = max(1, min(int(n), 20)), max(2, min(int(k), 5))
    st.update({"running": True, "done": 0, "total": 0, "client": client})

    def work():
        out = []
        try:
            from agent import heal, regression
            creds = heal._client_creds(client)
            if not creds:
                _save_run("consistency", {"client": client, "error": "Client connection details unavailable."}); return
            qs = top_questions(client, n)
            st["total"] = len(qs) * k
            if not qs:
                _save_run("consistency", {"client": client, "error": "No AI-answered questions found for this client in the last 30 days yet."}); return
            for q in qs:
                sets = []
                for _ in range(k):
                    try:
                        ans, res, info = regression._ask(creds, client, q)
                        sets.append(sorted(_figures(ans)))
                    except Exception as e:
                        sets.append(["error"])
                    st["done"] += 1
                stable = all(s == sets[0] for s in sets) and sets[0] != ["error"]
                out.append({"question": q, "stable": stable, "runs": [[str(x) for x in s][:8] for s in sets]})
            bad = [r for r in out if not r["stable"]]
            _save_run("consistency", {"client": client, "asked": len(out), "stable": len(out) - len(bad), "unstable": len(bad), "k": k, "results": out})
            if bad:
                _notify("Sahasra consistency check: %d unstable question(s) for %s" % (len(bad), client),
                        "Asking the same question several times gave different figures for %d question(s). See Admin > Settings > Accuracy checks." % len(bad))
        except Exception as e:
            _save_run("consistency", {"client": client, "error": str(e)[:200]})
        finally:
            st["running"] = False
    threading.Thread(target=work, daemon=True, name="consistency").start()
    return True


# ----------------------------------------------------------------------------- usage insights
def usage_insights(days=30):
    from agent import answer_log
    since = (datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)).isoformat(timespec="seconds")
    with answer_log._LOCK:
        c = answer_log._conn()
        try:
            clients = [dict(r) for r in c.execute(
                "SELECT client, COUNT(*) answers, SUM(CASE WHEN source='llm' THEN 1 ELSE 0 END) ai, "
                "SUM(CASE WHEN ok=0 THEN 1 ELSE 0 END) low, SUM(CASE WHEN vote='down' THEN 1 ELSE 0 END) down, "
                "SUM(CASE WHEN vote='up' THEN 1 ELSE 0 END) up FROM answer_log WHERE ts>=? GROUP BY client ORDER BY answers DESC LIMIT 100", (since,))]
            top = [dict(r) for r in c.execute(
                "SELECT question, COUNT(*) n, MAX(client) client FROM answer_log WHERE ts>=? AND question IS NOT NULL GROUP BY LOWER(question) ORDER BY n DESC LIMIT 12", (since,))]
            bad = [dict(r) for r in c.execute(
                "SELECT question, COUNT(*) n, MAX(client) client, AVG(score) score FROM answer_log WHERE ts>=? AND (ok=0 OR vote='down') AND question IS NOT NULL "
                "GROUP BY LOWER(question) ORDER BY n DESC LIMIT 12", (since,))]
        finally:
            c.close()
    for r in clients:
        a = r["answers"] or 1
        r["ai_pct"] = round(100 * (r["ai"] or 0) / a); r["low_pct"] = round(100 * (r["low"] or 0) / a)
    for r in bad:
        r["score"] = None if r["score"] is None else round(r["score"])
    return {"days": days, "clients": clients, "top": top, "problem": bad}


# ----------------------------------------------------------------------------- backups
def _wl_export():
    out = {}
    try:
        from auth import whitelabel
        from database.license_db import get_conn
        c = get_conn()
        try:
            ids = [int((r["id"] if hasattr(r, "items") else r[0])) for r in c.execute("SELECT id FROM institutions").fetchall()]
        finally:
            c.close()
        for i in ids:
            cfg = whitelabel.get_config(i)
            if cfg.get("configured"):
                out[str(i)] = {k: v for k, v in cfg.items() if k in whitelabel._DEFAULTS}
    except Exception as e:
        out["_error"] = str(e)[:200]
    return out


def make_backup(label="auto"):
    os.makedirs(BACKUPS, exist_ok=True)
    name = "backup-%s-%s.zip" % (_now().strftime("%Y%m%d-%H%M%S"), re.sub(r"[^a-z-]", "", label.lower())[:12] or "manual")
    path = os.path.join(BACKUPS, name)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for f in SQLITE_FILES:
            src = os.path.join(LOGS, f)
            if os.path.exists(src):
                tmp = path + "." + f + ".tmp"
                s = sqlite3.connect(src, timeout=10); d = sqlite3.connect(tmp)
                try:
                    s.backup(d)
                finally:
                    d.close(); s.close()
                z.write(tmp, "logs/" + f); os.remove(tmp)
        z.writestr("whitelabel.json", json.dumps(_wl_export(), indent=1, default=str))
        z.writestr("README.txt", "Sahasra settings backup %s. Contains Heal rules, scheduled reports, accuracy settings and white-label settings. "
                   "No passwords or API keys." % _now().isoformat(timespec="seconds"))
    files = sorted(f for f in os.listdir(BACKUPS) if f.startswith("backup-") and f.endswith(".zip"))
    for old in files[:-KEEP]:
        try:
            os.remove(os.path.join(BACKUPS, old))
        except Exception:
            pass
    return name


def list_backups():
    if not os.path.isdir(BACKUPS):
        return []
    out = []
    for f in sorted(os.listdir(BACKUPS), reverse=True):
        if f.startswith("backup-") and f.endswith(".zip"):
            p = os.path.join(BACKUPS, f)
            out.append({"name": f, "size_kb": round(os.path.getsize(p) / 1024), "ts": datetime.fromtimestamp(os.path.getmtime(p), IST).isoformat(timespec="seconds")})
    return out


def _safe_name(name):
    if not re.fullmatch(r"backup-[0-9]{8}-[0-9]{6}-[a-z-]*\.zip", name or ""):
        raise ValueError("Unknown backup.")
    p = os.path.join(BACKUPS, name)
    if not os.path.isfile(p):
        raise ValueError("Backup not found.")
    return p


def backup_bytes(name):
    with open(_safe_name(name), "rb") as f:
        return f.read()


def restore(name, admin="admin"):
    """Restores Heal rules / scheduled reports / these settings and white-label configs. Takes a 'pre-restore' backup first."""
    p = _safe_name(name)
    make_backup("pre-restore")
    done = []
    with zipfile.ZipFile(p) as z:
        for f in SQLITE_FILES:
            arc = "logs/" + f
            if arc in z.namelist():
                dst = os.path.join(LOGS, f)
                tmp = dst + ".restore"
                with open(tmp, "wb") as fh:
                    fh.write(z.read(arc))
                s = sqlite3.connect(tmp); d = sqlite3.connect(dst, timeout=20)
                try:
                    s.backup(d)
                finally:
                    d.close(); s.close(); os.remove(tmp)
                done.append(f)
        if "whitelabel.json" in z.namelist():
            from auth import whitelabel
            data = json.loads(z.read("whitelabel.json"))
            for iid, cfg in data.items():
                if iid.startswith("_"):
                    continue
                try:
                    whitelabel.save_config(int(iid), {k: v for k, v in cfg.items() if k not in ("institution_id", "configured", "updated_at", "updated_by")}, admin)
                    done.append("white-label #" + iid)
                except Exception:
                    pass
    try:
        from agent import answer_guard
        answer_guard.cache_clear(None)
    except Exception:
        pass
    return done


# ----------------------------------------------------------------------------- scheduler hook (called every minute)
_last = {"nightly": None, "backup": None}


def tick():
    try:
        cfg = get_cfg()
        hm, day = _now().strftime("%H:%M"), _now().strftime("%Y-%m-%d")
        if cfg["nightly_enabled"] and hm == cfg["nightly_time"] and _last["nightly"] != day:
            _last["nightly"] = day
            run_regression_bg(None, notify=True)
        if cfg["backup_enabled"] and hm == cfg["backup_time"] and _last["backup"] != day:
            _last["backup"] = day
            make_backup("auto")
    except Exception as e:
        print("[admin-extras] tick:", type(e).__name__, e)
    try:
        from agent import privacy
        privacy.tick()
    except Exception:
        pass
