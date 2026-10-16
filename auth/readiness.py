"""Client readiness check: for each institution, is the chatbot actually able to answer from ITS database?
Read-only. Per client: license active, database connects, the tables/columns the B2B portal needs exist, data is recent,
white-label settings are complete, B2B contacts point at real organisations. Plus server-wide checks (WhatsApp, OTP, SMTP).
Results are cached in logs/readiness.json; a full run happens in the background (6 clients at a time)."""
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FTimeout

_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs", "readiness.json")
_LOCK = threading.Lock()
STATE = {"running": False, "started": None, "done": 0, "total": 0}
PER_CLIENT_TIMEOUT = 45


def _load():
    try:
        with open(_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"clients": {}, "ts": None}


def _save(d):
    try:
        os.makedirs(os.path.dirname(_FILE), exist_ok=True)
        with open(_FILE, "w", encoding="utf-8") as f:
            json.dump(d, f)
    except Exception:
        pass


def _safe(e, n=140):
    s = str(e).replace("\n", " ")
    return s[:n]


def server_checks():
    out = []

    def add(st, key, text):
        out.append({"status": st, "key": key, "text": text})
    try:
        from notifications import whatsapp
        if whatsapp.configured():
            add("ok", "whatsapp", "WhatsApp (Pinnacle) is configured on this server.")
        else:
            add("fail", "whatsapp", "WhatsApp (Pinnacle) is NOT configured: set PINNACLE_WA_URL, PINNACLE_WA_APIKEY, PINNACLE_WA_FROM.")
    except Exception as e:
        add("warn", "whatsapp", "Could not check WhatsApp: " + _safe(e))
    prov = os.environ.get("B2B_OTP_PROVIDER", "twilio").strip().lower()
    if prov == "pinnacle":
        add("ok" if os.environ.get("PINNACLE_WA_OTP_TEMPLATE_ID") else "warn", "b2b_otp",
            "B2B login codes go over WhatsApp (Pinnacle)." + ("" if os.environ.get("PINNACLE_WA_OTP_TEMPLATE_ID") else
            " No approved OTP template id is set (PINNACLE_WA_OTP_TEMPLATE_ID): codes only reach people who messaged you in the last 24 h."))
    elif prov == "twilio":
        add("fail", "b2b_otp", "B2B login is still set to Twilio. Set B2B_OTP_PROVIDER=pinnacle.")
    else:
        add("warn", "b2b_otp", "B2B_OTP_PROVIDER is '%s'." % prov)
    try:
        from config import settings
        origins = list(settings.allowed_origins_list)
        if "*" in origins:
            add("fail", "cors", "Security: ALLOWED_ORIGINS allows every website ('*'). List only your own sites.")
        elif not origins:
            add("warn", "cors", "Security: ALLOWED_ORIGINS is empty - the widget on your website may be blocked.")
        else:
            add("ok", "cors", "Security: only %d listed website(s) may call the API." % len(origins))
    except Exception:
        pass
    try:
        from auth.admin_auth import TOKEN_TTL_SECONDS
        hrs = TOKEN_TTL_SECONDS / 3600.0
        add("ok" if hrs <= 24 else "warn", "session", "Security: admin sessions end after %s." % ("%d hours" % hrs if hrs >= 1 else "%d minutes" % (TOKEN_TTL_SECONDS // 60)) +
            ("" if hrs <= 24 else " Consider 12-24 hours."))
    except Exception:
        pass
    add("ok" if os.environ.get("SAHASRA_RATE_LIMIT", "1") != "0" else "warn", "ratelimit",
        "Security: public endpoints are rate-limited per visitor." if os.environ.get("SAHASRA_RATE_LIMIT", "1") != "0" else "Security: rate limiting is switched OFF (SAHASRA_RATE_LIMIT=0).")
    try:
        from notifications import mailer
        add("ok" if mailer.configured() else "warn", "email", "Email sending is configured." if mailer.configured() else
            "Email sending is not configured (needed for scheduled report emails and alerts).")
    except Exception:
        pass
    return out


def check_client(inst):
    """inst: row dict of institutions. Returns {prefix,name,level,modes,checks[]}."""
    checks = []

    def add(st, key, text):
        checks.append({"status": st, "key": key, "text": text})
    prefix = str(inst.get("client_prefix") or "")
    res = {"prefix": prefix, "name": inst.get("name") or prefix, "ts": time.time()}
    if str(inst.get("status") or "").lower() != "active":
        add("fail", "license", "Institution status is '%s' (must be active)." % (inst.get("status") or "unknown"))
    else:
        add("ok", "license", "Institution is active.")

    # --- white-label settings
    cfg = {}
    try:
        from auth.whitelabel import get_config
        cfg = get_config(int(inst["id"]))
    except Exception as e:
        add("warn", "wl", "Could not read white-label settings: " + _safe(e))
    if cfg:
        if not cfg.get("configured"):
            add("warn", "wl", "White-label settings have not been saved for this client yet (defaults apply).")
        elif not cfg.get("enabled"):
            add("warn", "wl", "White-label chatbot is switched OFF for this client.")
        else:
            add("ok", "wl", "White-label chatbot is on (B2C %s, B2B %s, admin %s)." % tuple(
                "on" if cfg.get(k) else "off" for k in ("b2c_enabled", "b2b_enabled", "admin_enabled")))
        if cfg.get("b2c_enabled") and cfg.get("enabled"):
            if (cfg.get("b2c_knowledge") or "").strip():
                add("ok", "b2c", "B2C knowledge text is filled in (%d characters)." % len(cfg["b2c_knowledge"]))
            else:
                add("warn", "b2c", "B2C is on but the knowledge text is empty - the public chatbot has nothing to answer from.")
    b2b_on = bool(cfg.get("configured") and cfg.get("enabled") and cfg.get("b2b_enabled"))

    # --- database
    if not (inst.get("db_name") and inst.get("db_server")):
        add("fail", "db", "Database name/server is not set for this client.")
        return _finish(res, checks, b2b_on)
    conn = None
    t0 = time.time()
    try:
        from database.connection import get_hospital_connection
        from auth.secrets_crypto import decrypt_secret
        pw = decrypt_secret(inst.get("db_password")) if inst.get("db_password") else None
        conn = get_hospital_connection(inst["db_name"], inst.get("db_server"), inst.get("db_user"), pw)
    except Exception as e:
        add("fail", "db", "Could not connect to the database: " + _safe(e))
    if conn is None and not any(c["key"] == "db" for c in checks):
        add("fail", "db", "Could not connect to the database (server offline, wrong login, or firewall).")
    if conn is None:
        return _finish(res, checks, b2b_on)
    try:
        cur = conn.cursor()
        add("ok", "db", "Database connects (%.1fs)." % (time.time() - t0))
        cur.execute("SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES")
        add("ok", "schema", "%d tables found." % int(cur.fetchone()[0]))

        def cols(table):
            cur.execute("SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = ?", (table,))
            return {str(r[0]).upper() for r in cur.fetchall()}
        bill = cols("trnINVLABPRI")
        if not bill:
            add("fail" if b2b_on else "warn", "billing", "Table trnINVLABPRI (lab billing) is missing - reports and B2B billing won't work here.")
        else:
            missing = {"BILLNO", "BILLDATE", "ORGANISATIONCODE"} - bill
            amt = next((c for c in ("TOTALCHARGES", "TOTALAMOUNT", "GRANDTOTAL") if c in bill), None)
            if missing:
                add("fail" if b2b_on else "warn", "billing", "trnINVLABPRI is missing column(s): " + ", ".join(sorted(missing)) + ".")
            elif not amt:
                add("fail" if b2b_on else "warn", "billing", "trnINVLABPRI has no billed-amount column the portal knows (TOTALCHARGES / TOTALAMOUNT / GRANDTOTAL).")
            else:
                add("ok", "billing", "Billing table is usable (amount column: %s)." % amt)
            try:
                cur.execute("SELECT MAX(BILLDATE) FROM trnINVLABPRI")
                mx = cur.fetchone()[0]
                if mx is None:
                    add("warn", "fresh", "No bills found in the billing table.")
                else:
                    from datetime import datetime
                    age = (datetime.now() - mx).days if hasattr(mx, "year") else None
                    if age is None:
                        add("ok", "fresh", "Latest bill: %s" % str(mx)[:10])
                    elif age > 7:
                        add("warn", "fresh", "Latest bill is %d days old (%s) - is this client still entering data?" % (age, str(mx)[:10]))
                    else:
                        add("ok", "fresh", "Latest bill is %s (data is fresh)." % str(mx)[:10])
            except Exception as e:
                add("warn", "fresh", "Could not read the latest bill date: " + _safe(e, 80))
        org = cols("mstOrganisation")
        if b2b_on:
            if not {"ORGANISATIONCODE", "ORGANISATIONNAME"}.issubset(org):
                add("fail", "org", "Table mstOrganisation (or its code/name columns) is missing - B2B can't verify organisations.")
            else:
                add("ok", "org", "Organisation master table is present.")
                try:
                    from database.license_db import get_conn
                    a = get_conn()
                    try:
                        rows = a.execute("SELECT organisation_code FROM dbo.sahasra_b2b_contacts WHERE institution_id=? AND active=1",
                                         (int(inst["id"]),)).fetchall()
                    finally:
                        a.close()
                    codes = sorted({str(r["organisation_code"] if hasattr(r, "items") else r[0]) for r in rows})
                    if not codes:
                        add("warn", "contacts", "B2B is on but no active B2B contacts are registered, so nobody can log in.")
                    else:
                        bad = []
                        for cde in codes[:25]:
                            cur.execute("SELECT TOP 1 1 FROM mstOrganisation WHERE ORGANISATIONCODE = ?", (cde,))
                            if cur.fetchone() is None:
                                bad.append(cde)
                        if bad:
                            add("fail", "contacts", "%d of %d B2B contact(s) point to an organisation code that does not exist: %s" %
                                (len(bad), len(codes[:25]), ", ".join(bad[:5])))
                        else:
                            add("ok", "contacts", "%d B2B organisation(s) registered and all exist in the database." % len(codes))
                except Exception as e:
                    add("warn", "contacts", "Could not check B2B contacts: " + _safe(e, 100))
    except Exception as e:
        add("fail", "db", "Database check failed: " + _safe(e))
    finally:
        try:
            conn.close()
        except Exception:
            pass
    return _finish(res, checks, b2b_on)


def _finish(res, checks, b2b_on):
    level = "fail" if any(c["status"] == "fail" for c in checks) else ("warn" if any(c["status"] == "warn" for c in checks) else "ok")
    res.update({"level": level, "b2b_on": b2b_on, "checks": checks})
    return res


def _institutions(prefix=None):
    from database.license_db import get_conn
    c = get_conn()
    try:
        if prefix:
            rows = c.execute("SELECT * FROM institutions WHERE UPPER(client_prefix)=UPPER(?)", (prefix,)).fetchall()
        else:
            rows = c.execute("SELECT * FROM institutions WHERE client_prefix IS NOT NULL AND client_prefix <> ''").fetchall()
        return [dict(r.items()) if hasattr(r, "items") else dict(r) for r in rows]
    finally:
        c.close()


def _run(prefix=None):
    try:
        insts = _institutions(prefix)
        STATE.update({"total": len(insts), "done": 0})
        data = _load()
        pool = ThreadPoolExecutor(max_workers=6)
        futs = {pool.submit(check_client, i): i for i in insts}
        for f, i in futs.items():
            try:
                r = f.result(timeout=PER_CLIENT_TIMEOUT * 2)
            except FTimeout:
                r = {"prefix": i.get("client_prefix"), "name": i.get("name"), "level": "fail", "ts": time.time(),
                     "checks": [{"status": "fail", "key": "db", "text": "The check timed out - the database did not answer."}]}
            except Exception as e:
                r = {"prefix": i.get("client_prefix"), "name": i.get("name"), "level": "fail", "ts": time.time(),
                     "checks": [{"status": "fail", "key": "db", "text": "Check failed: " + _safe(e)}]}
            data["clients"][str(r["prefix"]).upper()] = r
            STATE["done"] += 1
        pool.shutdown(wait=False)
        data["ts"] = time.time()
        _save(data)
    finally:
        STATE["running"] = False


def start(prefix=None):
    with _LOCK:
        if STATE["running"]:
            return False
        STATE.update({"running": True, "started": time.time(), "done": 0, "total": 0})
    threading.Thread(target=_run, args=(prefix,), daemon=True).start()
    return True


def summary():
    d = _load()
    cl = sorted(d["clients"].values(), key=lambda r: ({"fail": 0, "warn": 1, "ok": 2}.get(r.get("level"), 3), str(r.get("name"))))
    counts = {k: sum(1 for r in cl if r.get("level") == k) for k in ("ok", "warn", "fail")}
    return {"ts": d.get("ts"), "running": STATE["running"], "progress": {"done": STATE["done"], "total": STATE["total"]},
            "counts": counts, "server": server_checks(), "clients": cl}
