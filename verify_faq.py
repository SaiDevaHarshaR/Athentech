"""verify_faq.py - asks the chat common questions, runs an INDEPENDENT read-only SELECT on the lab DB,
and compares the numbers. Run from the app folder (uses the app's own DB connection + license lookup).

  python verify_faq.py --api https://api.athentech.in --code CM-ADMIN-13505 [--coll-col TOTALAMOUNT]

Only SELECT statements are ever run (the script refuses anything else). Nothing is written.
--coll-col: money column in trnMODEOFCOLLECTIONSDET for THIS lab (CM: TOTALAMOUNT, Konnect: PAIDAMOUNT).
Money may differ slightly if bills arrive between the chat call and the SQL; counts should match exactly.
"""
import argparse, json, re, sys, time, urllib.request
sys.path.insert(0, ".")
ap = argparse.ArgumentParser(); ap.add_argument("--api", required=True); ap.add_argument("--code", required=True)
ap.add_argument("--coll-col", default="auto"); ap.add_argument("--only", default="", help="regex: run only questions matching it"); a = ap.parse_args()
from auth.license_service import validate_license
from database.connection import get_hospital_connection
v = validate_license(a.code)
if not v.get("valid"): sys.exit("invalid code: %s" % v)
conn = get_hospital_connection(v.get("db_name"), v.get("db_server"), v.get("db_user"), v.get("db_password"))
if not conn: sys.exit("cannot connect to the lab DB")
C = a.coll_col
from agent.schema_ctx import get_profile, coll_amt, pri_amt
_p = get_profile(conn, v.get("db_name"), v.get("db_server"))
PRI = pri_amt(_p)
if C == "auto":      # use the app's own per-lab money rule (agent/schema_ctx.coll_amt), so we test the numbers, not the rule
    C = coll_amt(_p)
    print("money expression for this lab:", C)
M0 = "DATEADD(MONTH,DATEDIFF(MONTH,0,GETDATE()),0)"
L0 = "DATEADD(MONTH,DATEDIFF(MONTH,0,GETDATE())-1,0)"
T0 = "CAST(GETDATE() AS DATE)"
TOM = "DATEADD(DAY,1,CAST(GETDATE() AS DATE))"
# (question, sql, kind)  kind: money | count
WK0 = "DATEADD(DAY,-(DATEDIFF(DAY,'19000101',CAST(GETDATE() AS DATE))%7),CAST(GETDATE() AS DATE))"
YD = "DATEADD(DAY,-1,CAST(GETDATE() AS DATE))"
Y0 = "DATEADD(YEAR,DATEDIFF(YEAR,0,GETDATE()),0)"
D30 = "DATEADD(DAY,-29,CAST(GETDATE() AS DATE))"
RANGES = {  # name: (start, end)
 "today": (T0, TOM), "yesterday": (YD, T0), "this week": (WK0, TOM), "last week": (f"DATEADD(DAY,-7,{WK0})", WK0),
 "this month": (M0, TOM), "last month": (L0, M0), "this year": (Y0, TOM), "last 30 days": (D30, TOM)}
CASES = []
def add(q, sql, kind): CASES.append((q, sql, kind))
for nm, (a0, a1) in RANGES.items():
    add(f"total collection {nm}", f"SELECT SUM({C}) FROM trnMODEOFCOLLECTIONSDET WHERE DATEOFBILL >= {a0} AND DATEOFBILL < {a1}", "money")
    add(f"how many bills {nm}", f"SELECT COUNT(DISTINCT BILLNO) FROM trnINVLABPRI WHERE BILLDATE >= {a0} AND BILLDATE < {a1}", "count")
    add(f"how many tests {nm}", f"SELECT COUNT(*) FROM trninvlabdet WHERE BILLDATE >= {a0} AND BILLDATE < {a1}", "count")
    add(f"how many patients registered {nm}", f"SELECT COUNT(*) FROM mstPatientRegistration WHERE REGDATE >= {a0} AND REGDATE < {a1}", "count")
    add(f"sample rejections {nm}", f"SELECT COUNT(*) FROM trninvlabdet WHERE TESTSTATUS='Sample Rejected' AND BILLDATE >= {a0} AND BILLDATE < {a1}", "count")
    add(f"refunds {nm}", f"SELECT ISNULL(SUM(ABS({C})),0) FROM trnMODEOFCOLLECTIONSDET WHERE DATEOFBILL >= {a0} AND DATEOFBILL < {a1} AND TYPE LIKE '%Refund%'", "money")
for nm in ("today", "this month", "last month"):
    a0, a1 = RANGES[nm]
    add(f"total cash {nm}", f"SELECT SUM({C}) FROM trnMODEOFCOLLECTIONSDET WHERE UPPER(LTRIM(RTRIM(MODE)))='CASH' AND DATEOFBILL >= {a0} AND DATEOFBILL < {a1}", "money")
    add(f"total upi {nm}", f"SELECT SUM({C}) FROM trnMODEOFCOLLECTIONSDET WHERE UPPER(LTRIM(RTRIM(MODE)))='UPI' AND DATEOFBILL >= {a0} AND DATEOFBILL < {a1}", "money")
    add(f"top tests {nm}", f"SELECT TOP 1 COUNT(*) FROM trninvlabdet d WHERE d.BILLDATE >= {a0} AND d.BILLDATE < {a1} GROUP BY d.TCODE ORDER BY COUNT(*) DESC", "count")
    add(f"which branch collected the most {nm}", f"SELECT TOP 1 SUM({C}) FROM trnMODEOFCOLLECTIONSDET WHERE DATEOFBILL >= {a0} AND DATEOFBILL < {a1} GROUP BY LOCATIONID ORDER BY SUM({C}) DESC", "money")
    add(f"bills per doctor {nm}", f"SELECT TOP 1 COUNT(DISTINCT pr.BILLNO) FROM trnINVLABPRI pr LEFT JOIN mstrefdoctor doc ON pr.REFDOCTCODE=doc.DOCID WHERE pr.BILLDATE >= {a0} AND pr.BILLDATE < {a1} AND UPPER(ISNULL(doc.DOCNAME,'')) NOT LIKE '%SELF%' GROUP BY doc.DOCNAME ORDER BY COUNT(DISTINCT pr.BILLNO) DESC", "count")
    add(f"average bill value {nm}", f"SELECT SUM({PRI})/NULLIF(COUNT(DISTINCT BILLNO),0) FROM trnINVLABPRI pr WHERE BILLDATE >= {a0} AND BILLDATE < {a1}", "money")
    add(f"total billed value {nm}", f"SELECT SUM({PRI}) FROM trnINVLABPRI pr WHERE BILLDATE >= {a0} AND BILLDATE < {a1}", "money")
    add(f"ct scan {nm}", f"SELECT COUNT(*) FROM trninvlabdet d JOIN mstInvestigations i ON d.TCODE=i.INVCODE WHERE d.BILLDATE >= {a0} AND d.BILLDATE < {a1} AND i.INVNAME NOT LIKE '%CLOTT%' AND i.INVNAME NOT LIKE '%BLEEDING%' AND i.INVNAME NOT LIKE '%COAGUL%' AND (i.INVNAME LIKE 'CT %' OR i.INVNAME LIKE '% CT %' OR i.INVNAME LIKE '% CT' OR i.INVNAME LIKE 'CT-%' OR i.INVNAME LIKE '% CT-%' OR i.INVNAME LIKE '%CT SCAN%' OR i.INVNAME LIKE '%COMPUTED TOMO%' OR i.INVNAME = 'CT' OR i.INVNAME LIKE '%HRCT%' OR i.INVNAME LIKE '%NCCT%' OR i.INVNAME LIKE '%CECT%' OR i.INVNAME LIKE '%CT[0-9]%')", "count")
add("tat compliance last month", f"SELECT COUNT(*) FROM trnInvStatus s JOIN mstInvestigations inv ON s.TCODE=inv.INVCODE WHERE s.RESULTENTRYDATE >= {L0} AND s.RESULTENTRYDATE < {M0} AND s.SAMPLECOLLECTEDDATE IS NOT NULL AND s.RESULTENTRYDATE IS NOT NULL AND s.RESULTENTRYDATE >= s.SAMPLECOLLECTEDDATE AND DATEDIFF(MINUTE,s.SAMPLECOLLECTEDDATE,s.RESULTENTRYDATE) BETWEEN 0 AND 10080", "count")
add("tat compliance this month", f"SELECT COUNT(*) FROM trnInvStatus s JOIN mstInvestigations inv ON s.TCODE=inv.INVCODE WHERE s.RESULTENTRYDATE >= {M0} AND s.RESULTENTRYDATE < {TOM} AND s.SAMPLECOLLECTEDDATE IS NOT NULL AND s.RESULTENTRYDATE IS NOT NULL AND s.RESULTENTRYDATE >= s.SAMPLECOLLECTEDDATE AND DATEDIFF(MINUTE,s.SAMPLECOLLECTEDDATE,s.RESULTENTRYDATE) BETWEEN 0 AND 10080", "count")
add("list departments", "SELECT COUNT(*) FROM mstsubdepartment", "count")
add("active branches", "SELECT COUNT(*) FROM mstlocation WHERE ACTIVE = 1", "count")
def ask(q):
    req = urllib.request.Request(a.api.rstrip("/") + "/ask", json.dumps({"question": q, "activation_code": a.code, "chat_history": []}).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as r: body = r.read().decode("utf-8", "replace")
    try:
        j = json.loads(body); body = j.get("answer") or j.get("response") or body
    except Exception: pass
    try: body = json.loads('"%s"' % body.replace('"', '\\"')) if "\\u" in body else body
    except Exception: pass
    return str(body)
def nums(t):
    t = t.encode("utf-8", "ignore").decode("unicode_escape", "ignore") if "\\u" in t else t
    return [float(x.replace(",", "")) for x in re.findall(r"\d[\d,]*\.?\d*", t)]
ok = bad = 0
for q, sql, kind in CASES:
    if a.only and not re.search(a.only, q, re.I): continue
    assert sql.lstrip().upper().startswith("SELECT"), "read-only guard"
    try:
        ans = ask(q)
        cur = conn.cursor(); cur.execute(sql); rows_ = cur.fetchall(); cur.close(); exp = float(rows_[0][0] or 0) if rows_ else 0.0
    except Exception as e:
        print("ERROR %-42s %s" % (q, str(e)[:90])); bad += 1; continue
    got = nums(ans); tol = 0.005 * exp if kind == "money" else max(3, 0.002 * exp)
    real = [g for g in got if g not in (0, 2026, 7, 30, 10, 15)]
    hit = (exp == 0 and (not real or "no " in ans.lower())) or (exp != 0 and any(abs(g - exp) <= tol for g in got))
    if (not hit) or (exp == 0 and real): print("      chat said: %r" % re.sub(r"\s+", " ", ans)[:700])
    if not got: print("      (no numbers in chat answer; it said: %r)" % ans[:160])
    ok += hit; bad += (not hit)
    print("%-5s %-42s DB=%-14s chat_numbers=%s" % ("OK" if hit else "DIFF", q, "{:,.0f}".format(exp), [int(g) for g in got[:6]]))
print("\nMATCH %d / %d  (DIFF = look at it; small money diffs can be bills arriving during the run)" % (ok, ok + bad))
conn.close()
