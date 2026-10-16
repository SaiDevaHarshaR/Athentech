"""After a restart the first question from each hospital is slow (6-10 s) because its table layout and branch list are read for the first time.
This reads them in the background, one hospital at a time, for hospitals that were active in the last 7 days. Read-only; skip with SAHASRA_WARMUP=0."""
import os
import threading
import time


def _active_clients(days=7):
    try:
        import sqlite3
        from agent import answer_log as al
        c = sqlite3.connect(al._DB, timeout=5)
        try:
            return [r[0] for r in c.execute("SELECT DISTINCT client FROM answer_log WHERE ts > datetime('now', ?) AND client<>'unknown'", ("-%d day" % days,))]
        finally:
            c.close()
    except Exception:
        return []


def run(pause=2.0, limit=40):
    if os.getenv("SAHASRA_WARMUP", "1") == "0":
        return 0
    done = 0
    try:
        from agent import heal
        from database.connection import get_hospital_connection
        from agent.schema_ctx import get_profile, location_names
    except Exception:
        return 0
    for cl in _active_clients()[:limit]:
        try:
            cr = heal._client_creds(cl)
            if not cr or (cr.get("institution_type") or "") == "hospital":
                continue
            conn = get_hospital_connection(cr["db_name"], cr["db_server"], cr["db_user"], cr["db_password"])
            if not conn:
                continue
            try:
                get_profile(conn, cr["db_name"], cr["db_server"])
            finally:
                conn.close()
            location_names(cr["db_name"], cr["db_server"], cr["db_user"], cr["db_password"])
            done += 1
        except Exception:
            pass
        time.sleep(pause)
    print("[warmup] %d hospital(s) ready" % done, flush=True)
    return done


def start(delay=25):
    t = threading.Timer(delay, lambda: threading.Thread(target=run, daemon=True, name="warmup").start())
    t.daemon = True
    t.start()
