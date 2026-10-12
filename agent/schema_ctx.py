"""Per-institution schema profile, read straight from the client DB (no license DB).

Cached in-process per (server, db). Used by intents/tools so one codebase serves
Konnect (PAIDAMOUNT filled) and CentroMed (PAIDAMOUNT = 0, TOTALAMOUNT filled).
"""
import os
import time
import threading

_TTL = 6 * 3600
_cache = {}
_lock = threading.Lock()

_DEFAULTS = {
    "coll_metric": "paid",          # "paid" | "total"
    "coll_paid": "PAIDAMOUNT",
    "coll_total": "TOTALAMOUNT",
    "pri_paid": "PAIDAMOUNT",
    "pri_total": "TOTALCHARGES",
    "pat_date": "REGDATE",
    "pat_name": "NAME",
    "dept_src": "mstdepartment",    # "mstdepartment" | "mstsubdepartment"
    "pat_phones": ["PHONENO"],
}


def _cols(cur, table):
    cur.execute("SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = ?", (table,))
    return {str(r[0]).upper(): str(r[0]) for r in cur.fetchall()}


def _pick(cols, *names):
    for n in names:
        if n.upper() in cols:
            return cols[n.upper()]
    return None


def _scan(conn, db_name=None):
    p = dict(_DEFAULTS)
    cur = conn.cursor()
    try:
        cc = _cols(cur, "trnMODEOFCOLLECTIONSDET")
        pc = _cols(cur, "trnINVLABPRI")
        pt = _cols(cur, "mstPatientRegistration")
        p["coll_paid"] = _pick(cc, "PAIDAMOUNT", "PAIDAMT", "PAID")
        p["coll_total"] = _pick(cc, "TOTALAMOUNT", "TOTALCHARGES", "GRANDTOTAL", "AMOUNT")
        p["pri_paid"] = _pick(pc, "PAIDAMOUNT", "PAIDAMT")
        p["pri_total"] = _pick(pc, "TOTALCHARGES", "TOTALAMOUNT", "GRANDTOTAL")
        p["pat_date"] = _pick(pt, "REGDATE", "REGISTRATIONDATE", "CREATEDATE", "ENTRYDATE") or p["pat_date"]
        p["pat_name"] = _pick(pt, "NAME", "PATIENTNAME", "PATNAME") or p["pat_name"]
        p["pat_phones"] = [pt[c] for c in ("PHONENO", "MOBILENO", "MOBILE", "PHONE", "CONTACTNO", "MOBILENUMBER") if c in pt] or ["PHONENO"]

        # Metric = a client-wide habit, decided on ROW evidence (not money sums):
        # "total" only if PAIDAMOUNT is essentially never filled (<5% of rows that have a
        # total) over 90 days AND there are enough rows to trust it. Mixed clients
        # (walk-in + credit/corporate billing) and anything uncertain stay on "paid".
        dcol = _pick(cc, "DATEOFBILL", "BILLDATE")
        p["coll_metric"] = "paid"
        if p["coll_paid"] and p["coll_total"] and dcol:
            cur.execute(
                f"SELECT SUM(CASE WHEN ISNULL({p['coll_total']},0) <> 0 THEN 1 ELSE 0 END), "
                f"SUM(CASE WHEN ISNULL({p['coll_total']},0) <> 0 AND ISNULL({p['coll_paid']},0) <> 0 THEN 1 ELSE 0 END) "
                f"FROM trnMODEOFCOLLECTIONSDET WHERE {dcol} >= DATEADD(day,-90,GETDATE())")
            r = cur.fetchone()
            with_total, with_paid = int(r[0] or 0), int(r[1] or 0)
            p["rows_with_total_90d"], p["rows_with_paid_90d"] = with_total, with_paid
            if with_total >= 20 and with_paid < with_total * 0.05:
                p["coll_metric"] = "total"
        elif not p["coll_paid"] and p["coll_total"]:
            p["coll_metric"] = "total"

        # radiology department source: whichever table actually matches trninvlabdet.DEPTCODE
        for src, idc, namec in (("mstdepartment", "DEPARTMENTID", "DEPARTMENTNAME"),
                                ("mstsubdepartment", "SubDepartmentID", "SubDeptName")):
            try:
                cur.execute(
                    f"SELECT TOP 1 1 FROM trninvlabdet WHERE DEPTCODE IN "
                    f"(SELECT {idc} FROM {src} WHERE {namec} LIKE '%Radiology%')")
                if cur.fetchone():
                    p["dept_src"] = src
                    break
            except Exception:
                continue
        # explicit override wins (ops escape hatch): COLLECTION_METRIC_OVERRIDE="H023-CentromedLIS=total,H022-KonnectLIS=paid"
        ov = {k.strip().casefold(): v.strip().lower() for k, _, v in
              (x.partition("=") for x in os.environ.get("COLLECTION_METRIC_OVERRIDE", "").split(",")) if k.strip()}
        o = ov.get((db_name or "").casefold())
        if o in ("paid", "total"):
            p["coll_metric"] = o
        p["facts"] = _facts(cur, p)
    except Exception as e:
        print(f"[schema_ctx] scan failed, using defaults: {e}", flush=True)
    return p


def _q(cur, sql, n=40):
    try:
        try:
            cur.timeout = 20
        except Exception:
            pass
        cur.execute(sql)
        return cur.fetchmany(n)
    except Exception as e:
        print(f"[schema_ctx] fact query skipped: {str(e)[:120]}", flush=True)
        return []


def _facts(cur, p):
    """Real values from THIS client's data (last 90 days) so the LLM stops guessing."""
    f = {}
    rows = _q(cur, "SELECT TOP 30 TESTSTATUS, COUNT(*) FROM trninvlabdet "
                   "WHERE BILLDATE >= DATEADD(day,-90,GETDATE()) GROUP BY TESTSTATUS ORDER BY 2 DESC")
    f["test_statuses"] = [f"{r[0]} ({r[1]})" for r in rows if r[0]]
    rows = _q(cur, f"SELECT TOP 30 TYPE, COUNT(*), SUM({coll_amt(p)}) FROM trnMODEOFCOLLECTIONSDET "
                   f"WHERE DATEOFBILL >= DATEADD(day,-90,GETDATE()) GROUP BY TYPE ORDER BY 2 DESC")
    f["collection_types"] = [f"{r[0]} ({r[1]} rows)" for r in rows if r[0]]
    rows = _q(cur, "SELECT TOP 30 MODE, COUNT(*) FROM trnMODEOFCOLLECTIONSDET "
                   "WHERE DATEOFBILL >= DATEADD(day,-90,GETDATE()) GROUP BY MODE ORDER BY 2 DESC")
    f["payment_modes"] = [f"{r[0]} ({r[1]})" for r in rows if r[0]]
    rows = _q(cur, "SELECT COUNT(*), SUM(CASE WHEN ISNULL(RefundAmt,0)>0 THEN 1 ELSE 0 END) FROM trnINVLABPRI "
                   "WHERE BILLDATE >= DATEADD(day,-90,GETDATE())")
    if rows:
        f["bills_90d"], f["bills_with_refundamt_90d"] = int(rows[0][0] or 0), int(rows[0][1] or 0)
    if p["dept_src"] == "mstsubdepartment":
        j, nm, idc = "mstsubdepartment dep", "dep.SubDeptName", "dep.SubDepartmentID"
    else:
        j, nm, idc = "mstdepartment dep", "dep.DEPARTMENTNAME", "dep.DEPARTMENTID"
    rows = _q(cur, f"SELECT TOP 25 d.DEPTCODE, {nm}, COUNT(*) FROM trninvlabdet d "
                   f"LEFT JOIN {j} ON {idc} = d.DEPTCODE WHERE d.BILLDATE >= DATEADD(day,-30,GETDATE()) "
                   f"GROUP BY d.DEPTCODE, {nm} ORDER BY 3 DESC")
    f["departments_30d"] = [f"{r[0]}={r[1]} ({r[2]} tests)" for r in rows]
    mods = {}
    for label, pat in (("CT", "%CT %"), ("MRI", "%MRI%"), ("X-Ray", "%X-RAY%"), ("Ultrasound", "%ULTRASOUND%")):
        r = _q(cur, "SELECT COUNT(*) FROM trninvlabdet d JOIN mstInvestigations i ON d.TCODE = i.INVCODE "
                    "WHERE d.BILLDATE >= DATEADD(day,-90,GETDATE()) AND i.INVNAME LIKE '" + pat + "'", 1)
        mods[label] = int(r[0][0]) if r else None
    f["modality_tests_90d"] = mods
    return f


def get_profile(conn, db_name, db_server=None):
    key = f"{db_server or ''}|{db_name}"
    now = time.time()
    with _lock:
        hit = _cache.get(key)
        if hit and now - hit[0] < _TTL:
            return hit[1]
    p = _scan(conn, db_name)
    with _lock:
        _cache[key] = (now, p)
    print(f"[schema_ctx] {db_name}: {p}", flush=True)
    return p


def coll_amt(p, alias=""):
    """SQL expression for 'collection amount' on trnMODEOFCOLLECTIONSDET (never references a missing column)."""
    a = f"{alias}." if alias else ""
    paid = f"{a}{p['coll_paid']}" if p.get("coll_paid") else None
    total = f"{a}{p['coll_total']}" if p.get("coll_total") else None
    if not paid and not total:
        return "0"
    if not paid:
        return f"ISNULL({total},0)"
    if not total or p["coll_metric"] == "paid":
        return f"ISNULL({paid},0)"
    return f"(CASE WHEN ISNULL({paid},0) <> 0 THEN {paid} ELSE ISNULL({total},0) END)"


def pri_amt(p, alias=""):
    """SQL expression for per-bill amount on trnINVLABPRI."""
    a = f"{alias}." if alias else ""
    col = (p.get("pri_total") if p["coll_metric"] == "total" else p.get("pri_paid")) or p.get("pri_paid") or p.get("pri_total")
    return f"ISNULL({a}{col},0)" if col else "0"


def radiology_dept_sql(p, name="Radiology", col="DEPTCODE"):
    name = "".join(ch for ch in str(name) if ch.isalnum() or ch in " -&")
    if p["dept_src"] == "mstsubdepartment":
        return (f"{col} IN (SELECT SubDepartmentID FROM mstsubdepartment "
                f"WHERE SubDeptName LIKE '%{name}%')")
    return (f"{col} IN (SELECT DEPARTMENTID FROM mstdepartment "
            f"WHERE DEPARTMENTNAME LIKE '%{name}%')")


# ---- branch names come from each client's own mstLocation (never hardcoded) ----
_loc_cache = {}


def location_names(db_name, db_server=None, db_user=None, db_password=None):
    """Lower-cased branch names for this client, longest first. Cached 6h; [] on any failure."""
    key = f"{db_server or ''}|{db_name}"
    now = time.time()
    with _lock:
        hit = _loc_cache.get(key)
        if hit and now - hit[0] < _TTL:
            return hit[1]
    names = []
    try:
        from database.connection import get_hospital_connection
        conn = get_hospital_connection(db_name, db_server, db_user, db_password)
        if conn:
            try:
                cur = conn.cursor()
                cur.execute("SELECT DISTINCT LOCATIONNAME FROM mstlocation")
                import re as _re
                seen = set()
                for (n,) in cur.fetchall():
                    n = (n or "").strip().lower()
                    if not n:
                        continue
                    seen.add(n)
                    short = _re.sub(r"\s*\(.*?\)\s*", " ", n).strip()   # "central lab(hyd)" -> "central lab"
                    if len(short) >= 3:
                        seen.add(short)
                names = sorted(seen, key=len, reverse=True)
            finally:
                conn.close()
    except Exception as e:
        print(f"[schema_ctx] location_names failed: {e}", flush=True)
    with _lock:
        _loc_cache[key] = (now, names)
    return names


def location_regex(names, prefix=""):
    """Compiled-ready pattern matching any known branch name; never matches when names is empty."""
    import re as _re
    if not names:
        return r"(?!x)x"
    return prefix + r"(" + "|".join(_re.escape(n) for n in names) + r")\b"



def data_map_text(p, branch_names=None):
    """Authoritative per-client data map for the LLM (built from the live profile, no client names)."""
    phones = ", ".join(p.get("pat_phones") or ["PHONENO"])
    rad = radiology_dept_sql(p, "Radiology", "d.DEPTCODE")
    br = ""
    if branch_names:
        br = " Known branches: " + ", ".join(sorted({n for n in branch_names if "(" not in n})[:40]) + "."
    return f"""CLIENT DATA MAP — AUTHORITATIVE. It overrides any older instruction above that conflicts with it.
- COLLECTION / REVENUE / PAYMENT MODES: table trnMODEOFCOLLECTIONSDET m. Date m.DATEOFBILL, mode m.MODE, bill m.BILLNO,
  branch m.LOCATIONID -> mstLocation.LOCATIONID / LOCATIONNAME. Amount expression for THIS client (use exactly): {coll_amt(p, 'm')}
  Refunds: m.TYPE = 'LabRefund'. Daily trend: GROUP BY CAST(m.DATEOFBILL AS date). NEVER use msttally*, msttemp* or trntemp* tables for collections.
- BILLS (header): trnINVLABPRI pr: BILLNO, BILLDATE, TOTALCHARGES, CONCESSIONAMT, CREDITAMOUNT, RefundAmt, STATUS, REFDOCTCODE -> mstrefdoctor.DOCID / DOCNAME. Bill amount for THIS client: {pri_amt(p, 'pr')}
- TESTS ON A BILL: trnINVLABDET d: BILLNO, BILLDATE, TCODE -> mstInvestigations.INVCODE / INVNAME, DEPTCODE, TESTSTATUS, LOCATIONID.
  Before filtering on TESTSTATUS run SELECT DISTINCT TESTSTATUS to see this client's real values (e.g. cancelled).
- RADIOLOGY / MODALITY: trnINVLABDET d with {rad}; modality by mstInvestigations.INVNAME LIKE '%CT%', '%MRI%', '%X-RAY%', '%ULTRASOUND%'. Branch = d.LOCATIONID -> mstLocation.
- TAT / TURNAROUND: ALWAYS call get_tat_compliance_dashboard or check_tat_alert (period accepts today, yesterday, this_week, last_week, this_month, last_month, this_year, month:YYYY-MM, year:YYYY). Do NOT hand-write TAT SQL; trnparamresult.CREATEDATE rules above do not apply.
- PATIENTS: mstPatientRegistration: UHID, {p['pat_name']} (name), {p['pat_date']} (registered on), phone: {phones}. Visits/repeat patients come from BILLS (trnINVLABPRI grouped by UHID), not registrations.
{facts_block(p)}
- Aggregate in SQL (COUNT/SUM/GROUP BY), never SELECT thousands of rows. Add TOP when listing. If a query errors, read the error, fix the column from describe_table, and retry once before giving up.{br}"""


def facts_block(p):
    f = p.get("facts") or {}
    if not f:
        return ""
    out = ["REAL VALUES FOUND IN THIS CLIENT'S DATA (last 30-90 days) — trust these over guesses:"]
    if f.get("test_statuses"):
        out.append("- trnINVLABDET.TESTSTATUS values: " + "; ".join(f["test_statuses"]) +
                   ". Cancellations/rejections/pending are counted ONLY from these values (e.g. 'Sample Rejected'); do not invent a status or a rejection table.")
    if f.get("collection_types"):
        out.append("- trnMODEOFCOLLECTIONSDET.TYPE values: " + "; ".join(f["collection_types"]))
    if f.get("payment_modes"):
        out.append("- Payment MODE values: " + "; ".join(f["payment_modes"]))
    if "bills_90d" in f:
        out.append(f"- Refunds: {f['bills_with_refundamt_90d']} of {f['bills_90d']} bills in 90 days have trnINVLABPRI.RefundAmt > 0; "
                   "TYPE values above show whether refund rows exist in the collection table. Check BOTH sources before saying there are no refunds.")
    if f.get("departments_30d"):
        out.append("- DEPTCODE=department name (tests, last 30d): " + "; ".join(f["departments_30d"]))
    if f.get("modality_tests_90d"):
        out.append("- Tests matching modality names in INVNAME (90d): " + ", ".join(f"{k}={v}" for k, v in f["modality_tests_90d"].items())
                   + ". If a modality shows 0/None, say it is not performed/recorded here instead of guessing other columns.")
    return "\n".join(out)
