"""Run from the app folder:  python patch_b2b_reliability.py   (backs up auth/b2b_portal.py; all-or-nothing; idempotent)"""
import shutil, sys, time
P = "auth/b2b_portal.py"
MARK = "# [b2b-reliability-v1]"
s = open(P, encoding="utf-8").read()
if MARK in s:
    print("ALREADY APPLIED"); sys.exit(0)

PAIRS = [
# 1. rate limiter: prune empty buckets so scanners can't grow memory forever
("""        if len(bucket) >= max_attempts:
            raise HTTPException(429, "Too many attempts. Please try again later.")
        bucket.append(now)
""",
"""        if len(bucket) >= max_attempts:
            raise HTTPException(429, "Too many attempts. Please try again later.")
        bucket.append(now)
        if len(_hits) > 5000:  # [b2b-reliability-v1] drop expired buckets
            for k in [k for k, b in _hits.items() if not b or now - b[-1] >= 3600]:
                _hits.pop(k, None)
"""),
# 2. language-neutral date parameters + cached column lookups + friendly labels
("""def _columns(conn, table):
    rows = conn.execute("SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = ?", (table,)).fetchall()
    return {str(r[0]).upper() for r in rows}
""",
"""def _dt(iso):
    \"\"\"datetime object for SQL parameters. A 'YYYY-MM-DD' string compared with a datetime column is
    language/DATEFORMAT dependent on SQL Server (dmy sessions read it as YYYY-DD-MM); a datetime is not.\"\"\"
    return datetime.fromisoformat(iso)


def _period_label(period, start, end):
    \"\"\"Human-readable period with the real date range, e.g. 'this month (01 Oct - 15 Oct 2026)'.\"\"\"
    try:
        a = date.fromisoformat(start); b = date.fromisoformat(end) - timedelta(days=1)
        rng = a.strftime("%d %b %Y") if a == b else a.strftime("%d %b") + " - " + b.strftime("%d %b %Y")
    except ValueError:
        return str(period)
    name = str(period).replace("_", " ")
    return name + " (" + rng + ")" if name != rng else rng


def _columns(conn, table):
    cache = getattr(conn, "_b2b_cols", None)
    if cache is not None and table in cache:
        return cache[table]
    rows = conn.execute("SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = ?", (table,)).fetchall()
    cols = {str(r[0]).upper() for r in rows}
    try:
        if cache is None:
            conn._b2b_cols = cache = {}
        cache[table] = cols
    except Exception:  # connection objects that forbid attributes: just don't cache
        pass
    return cols
"""),
("""        rows = conn.execute(sql, (organisation_code, start, end)).fetchall()
        return [(str(r[0]), str(r[1])[:19], float(r[2] or 0), str(r[3] or "Not specified")) for r in rows]""",
"""        rows = conn.execute(sql, (organisation_code, _dt(start), _dt(end))).fetchall()
        return [(str(r[0]), str(r[1])[:19], float(r[2] or 0), str(r[3] or "Not specified")) for r in rows]"""),
("""            "FROM trnINVLABPRI p WHERE p.ORGANISATIONCODE = ? "
            "AND p.BILLDATE >= ? AND p.BILLDATE < ?", (org_code, start, end)).fetchone()""",
"""            "FROM trnINVLABPRI p WHERE p.ORGANISATIONCODE = ? "
            "AND p.BILLDATE >= ? AND p.BILLDATE < ?", (org_code, _dt(start), _dt(end))).fetchone()"""),
("""                "GROUP BY p.STATUS", (org_code, start, end)).fetchall()""",
"""                "GROUP BY p.STATUS", (org_code, _dt(start), _dt(end))).fetchall()"""),
("""                "GROUP BY d.TESTSTATUS", (org_code, org_code, start, end)).fetchall()""",
"""                "GROUP BY d.TESTSTATUS", (org_code, org_code, _dt(start), _dt(end))).fetchall()"""),
# 3. summary: also report the real date label
("""                   "amount_label": "Billed amount (not collected cash)", "from": start, "to_exclusive": end}""",
"""                   "amount_label": "Billed amount (not collected cash)", "from": start, "to_exclusive": end,
                   "period_label": _period_label(period, start, end)}"""),
# 4. chat: friendly errors, honest counts, status breakdown in the text
("""        if intent == "overview":
            summary = _summary_for_org(inst, org, requested_period)
            return {"status": "success", "intent": intent, "summary": summary,
                    "answer": (f"For {requested_period}: {summary['bills']} invoices, "
                               f"billed amount INR {summary['billed_total']:,.2f}. "
                               "This is billed value, not collected cash. See the summary for status details.")}
        if intent == "bills":
            rows = _rows_for_org(inst, org, requested_period, max_rows=20)
            return {"status": "success", "intent": intent,
                    "bills": [{"bill_no": b, "bill_date": dt, "billed_amount": amount, "status": st}
                              for b, dt, amount, st in rows[:20]], "has_more": len(rows) > 20,
                    "answer": f"Found {min(len(rows),20)} invoice records for your organization in {requested_period}."}""",
"""        if intent in ("overview", "bills"):
            try:
                _period_dates(requested_period)
            except HTTPException:
                requested_period = body.period if body.period else "this_month"  # unparseable phrase -> selected period
            try:
                if intent == "overview":
                    summary = _summary_for_org(inst, org, requested_period)
                    label = summary.get("period_label") or requested_period
                    text = (f"For {label}: {summary.get('bills', 0)} invoice{'s' if summary.get('bills', 0) != 1 else ''}, "
                            f"billed amount INR {summary.get('billed_total', 0):,.2f}. "
                            "This is billed value, not collected cash.")
                    if summary.get("bills") == 0:
                        text = f"No invoices were found for your organization in {label}."
                    elif summary.get("invoice_statuses"):
                        text += " By status: " + ", ".join(
                            f"{x['status']} {x['bills']}" for x in summary["invoice_statuses"][:6]) + "."
                    return {"status": "success", "intent": intent, "summary": summary, "answer": text}
                rows = _rows_for_org(inst, org, requested_period, max_rows=20)
                s_, e_ = _period_dates(requested_period)
                label = _period_label(requested_period, s_, e_)
                shown = min(len(rows), 20)
                if not rows:
                    text = f"No invoices were found for your organization in {label}."
                elif len(rows) > 20:
                    text = f"Showing the latest {shown} invoices for {label}. More exist: download the Excel report for the full list."
                else:
                    text = f"Found {shown} invoice{'s' if shown != 1 else ''} for your organization in {label}."
                return {"status": "success", "intent": intent,
                        "bills": [{"bill_no": b, "bill_date": dt, "billed_amount": amount, "status": st}
                                  for b, dt, amount, st in rows[:20]], "has_more": len(rows) > 20, "answer": text}
            except HTTPException as exc:
                if exc.status_code in (400, 422, 503):  # schema / config problem: say so instead of a bare error
                    return {"status": "success", "intent": intent, "answer": str(exc.detail)}
                raise
            except Exception:
                return {"status": "success", "intent": intent,
                        "answer": "I couldn't read your organization's records just now. Please try again in a minute."}"""),
]
new = s
for i, (a, b) in enumerate(PAIRS, 1):
    if new.count(a) != 1:
        print(f"ANCHOR {i} not found exactly once (found {new.count(a)}). Nothing changed."); sys.exit(1)
    new = new.replace(a, b)
new = new.replace('"""Sahasra white-label B2B', MARK + '\n"""Sahasra white-label B2B', 1) if False else new + "\n" + MARK + "\n"
bak = P + ".bak-" + time.strftime("%Y%m%d-%H%M%S")
shutil.copy2(P, bak)
open(P, "w", encoding="utf-8").write(new)
print("APPLIED. backup:", bak)
