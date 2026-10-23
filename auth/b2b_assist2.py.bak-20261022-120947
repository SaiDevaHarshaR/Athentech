"""B2B assistant, part 2: operational analytics for the verified organisation (pending / delayed / rejection / top tests /
branch volume / trend / TAT performance / invoices / due date). Fixed read-only queries bound to the organisation code.
route2(Q, org, q, p, bill) -> response dict or None (None = let the other handlers / the AI answer)."""
import re
from datetime import date, timedelta
from auth.b2b_assist import _inr, _d, _dates, _label, _out, _tbl, _status_for_period

_DONE = "LOWER(ISNULL(s.STATUS,'')) LIKE 'authent%'"
_REJ = "LOWER(ISNULL(s.STATUS,'')) LIKE '%reject%'"


def _pending_list(Q, org, p):
    a, b = _dates(p)
    rows = Q("SELECT TOP 25 s.BILLNO, ISNULL(m.INVNAME, s.TCODE), s.STATUS, pr.BILLDATE FROM trnInvStatus s JOIN trnINVLABPRI pr ON pr.BILLNO = s.BILLNO "
             "LEFT JOIN mstInvestigations m ON m.INVCODE COLLATE DATABASE_DEFAULT = s.TCODE COLLATE DATABASE_DEFAULT "
             "WHERE pr.ORGANISATIONCODE = ? AND pr.BILLDATE >= ? AND pr.BILLDATE < ? AND NOT (" + _DONE + ") AND NOT (" + _REJ + ") ORDER BY pr.BILLDATE", (org, a, b))
    n = Q("SELECT COUNT(*) FROM trnInvStatus s JOIN trnINVLABPRI pr ON pr.BILLNO = s.BILLNO WHERE pr.ORGANISATIONCODE = ? AND pr.BILLDATE >= ? AND pr.BILLDATE < ? "
          "AND NOT (" + _DONE + ") AND NOT (" + _REJ + ")", (org, a, b))
    tot = int(n[0][0] or 0) if n else 0
    if not rows:
        return _out("pending", "No pending tests for your organisation %s - all have final reports." % _label(p))
    return _out("pending", "**%d** tests are still pending %s%s." % (tot, _label(p), " (showing the oldest %d)" % len(rows) if tot > len(rows) else ""),
                _tbl("Pending tests", ["Bill", "Test", "Stage", "Bill date"], [[r[0], r[1], r[2] or "", _d(r[3])] for r in rows]),
                suggestions=["Raise a delay complaint"])


def _delayed(Q, org):
    rows = Q("SELECT TOP 25 s.BILLNO, ISNULL(m.INVNAME, s.TCODE), s.STATUS, pr.BILLDATE FROM trnInvStatus s JOIN trnINVLABPRI pr ON pr.BILLNO = s.BILLNO "
             "LEFT JOIN mstInvestigations m ON m.INVCODE COLLATE DATABASE_DEFAULT = s.TCODE COLLATE DATABASE_DEFAULT "
             "WHERE pr.ORGANISATIONCODE = ? AND pr.BILLDATE >= DATEADD(day,-30,GETDATE()) AND pr.BILLDATE < DATEADD(day,-1,GETDATE()) "
             "AND NOT (" + _DONE + ") AND NOT (" + _REJ + ") ORDER BY pr.BILLDATE", (org,))
    if not rows:
        return _out("delayed", "Good news: no test from the last 30 days has been pending for more than 24 hours.")
    return _out("delayed", "These tests have been pending for **more than 24 hours** (oldest first) and are the most likely to be delayed:",
                _tbl("Possibly delayed tests", ["Bill", "Test", "Stage", "Bill date"], [[r[0], r[1], r[2] or "", _d(r[3])] for r in rows]),
                suggestions=["Raise a delay complaint", "Talk to lab manager"])


def _rejection(Q, org, p):
    a, b = _dates(p)
    r = Q("SELECT COUNT(*), SUM(CASE WHEN " + _REJ + " THEN 1 ELSE 0 END) FROM trnInvStatus s JOIN trnINVLABPRI pr ON pr.BILLNO = s.BILLNO "
          "WHERE pr.ORGANISATIONCODE = ? AND pr.BILLDATE >= ? AND pr.BILLDATE < ?", (org, a, b))
    tot, rej = (int(r[0][0] or 0), int(r[0][1] or 0)) if r else (0, 0)
    if not tot:
        return _out("rejection", "No tests found for your organisation %s." % _label(p))
    return _out("rejection", "Sample rejection %s: **%d of %d** tests (**%.2f%%**)." % (_label(p), rej, tot, rej * 100.0 / tot),
                suggestions=["Show rejected samples"])


def _top_tests(Q, org, p):
    a, b = _dates(p)
    rows = Q("SELECT TOP 10 ISNULL(m.INVNAME, s.TCODE), COUNT(*) FROM trnInvStatus s JOIN trnINVLABPRI pr ON pr.BILLNO = s.BILLNO "
             "LEFT JOIN mstInvestigations m ON m.INVCODE COLLATE DATABASE_DEFAULT = s.TCODE COLLATE DATABASE_DEFAULT "
             "WHERE pr.ORGANISATIONCODE = ? AND pr.BILLDATE >= ? AND pr.BILLDATE < ? GROUP BY ISNULL(m.INVNAME, s.TCODE) ORDER BY COUNT(*) DESC", (org, a, b))
    if not rows:
        return _out("top_tests", "No tests found for your organisation %s." % _label(p))
    return _out("top_tests", "Most frequently ordered tests %s - **%s** leads with %s." % (_label(p), rows[0][0], format(int(rows[0][1]), ",")),
                _tbl("Top tests", ["Test", "Count"], [[r[0], r[1]] for r in rows]))


def _branch_volume(Q, org, p):
    a, b = _dates(p)
    rows = Q("SELECT TOP 10 COALESCE(l.LOCATIONNAME, CAST(pr.LocationId AS VARCHAR(40)), 'Unknown'), COUNT(DISTINCT pr.BILLNO) FROM trnINVLABPRI pr "
             "LEFT JOIN mstlocation l ON l.LOCATIONID = pr.LocationId WHERE pr.ORGANISATIONCODE = ? AND pr.BILLDATE >= ? AND pr.BILLDATE < ? "
             "GROUP BY COALESCE(l.LOCATIONNAME, CAST(pr.LocationId AS VARCHAR(40)), 'Unknown') ORDER BY COUNT(DISTINCT pr.BILLNO) DESC", (org, a, b))
    if not rows:
        return _out("branch", "No bills found for your organisation %s." % _label(p))
    return _out("branch", "Busiest branch for your orders %s: **%s** (%s bills)." % (_label(p), rows[0][0], format(int(rows[0][1]), ",")),
                _tbl("Bills by branch", ["Branch", "Bills"], [[r[0], r[1]] for r in rows]))


def _trend(Q, org):
    t = date.today()
    start = (t.replace(day=1) - timedelta(days=1)).replace(day=1)
    start = (start - timedelta(days=1)).replace(day=1)          # first day of the month two months ago
    rows = Q("SELECT YEAR(pr.BILLDATE), MONTH(pr.BILLDATE), COUNT(DISTINCT pr.BILLNO), SUM(CAST(ISNULL(pr.TOTALCHARGES,0) AS FLOAT)) FROM trnINVLABPRI pr "
             "WHERE pr.ORGANISATIONCODE = ? AND pr.BILLDATE >= ? AND pr.BILLDATE < ? GROUP BY YEAR(pr.BILLDATE), MONTH(pr.BILLDATE) ORDER BY 1, 2",
             (org, start.isoformat(), (t + timedelta(days=1)).isoformat()))
    if not rows:
        return _out("trend", "No billing found for your organisation in the last three months.")
    names = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    body = [["%s %s" % (names[int(r[1])], r[0]), r[2], _inr(r[3])] for r in rows]
    msg = "Last three months for your organisation (current month is partial)."
    if len(rows) >= 2 and float(rows[-2][3] or 0) > 0:
        ch = (float(rows[-1][3] or 0) - float(rows[-2][3] or 0)) * 100.0 / float(rows[-2][3])
        msg += " This month so far is **%+.1f%%** versus the previous month's total." % ch
    return _out("trend", msg, _tbl("Monthly trend", ["Month", "Bills", "Billed amount"], body))


def _billing_total(Q, org, p):
    a, b = _dates(p)
    r = Q("SELECT COUNT(DISTINCT BILLNO), SUM(CAST(ISNULL(TOTALCHARGES,0) AS FLOAT)) FROM trnINVLABPRI WHERE ORGANISATIONCODE = ? AND BILLDATE >= ? AND BILLDATE < ?", (org, a, b))
    n, v = (int(r[0][0] or 0), float(r[0][1] or 0)) if r else (0, 0.0)
    return _out("billing_total", "Your billed total %s: **%s** across **%s** bills. This is billed value, not cash received." % (_label(p), _inr(v), format(n, ",")),
                suggestions=["Billing statement", "Download Excel"])


def _tat_performance(Q, org, p):
    a, b = _dates(p)
    r = Q("SELECT COUNT(*), SUM(CASE WHEN DATEDIFF(hour, s.SAMPLECOLLECTEDDATE, s.AUTHENTICATEDATE) <= 24 THEN 1 ELSE 0 END), "
          "SUM(CASE WHEN DATEDIFF(hour, s.SAMPLECOLLECTEDDATE, s.AUTHENTICATEDATE) <= 48 THEN 1 ELSE 0 END), "
          "AVG(CAST(DATEDIFF(minute, s.SAMPLECOLLECTEDDATE, s.AUTHENTICATEDATE) AS FLOAT)) FROM trnInvStatus s JOIN trnINVLABPRI pr ON pr.BILLNO = s.BILLNO "
          "WHERE pr.ORGANISATIONCODE = ? AND pr.BILLDATE >= ? AND pr.BILLDATE < ? AND s.AUTHENTICATEDATE IS NOT NULL AND s.SAMPLECOLLECTEDDATE IS NOT NULL "
          "AND s.AUTHENTICATEDATE >= s.SAMPLECOLLECTEDDATE", (org, a, b))
    n = int(r[0][0] or 0) if r else 0
    if not n:
        return _out("tat", "There are no completed tests with recorded collection and authentication times %s." % _label(p))
    w24, w48, avg = int(r[0][1] or 0), int(r[0][2] or 0), float(r[0][3] or 0)
    return _out("tat", "For **%s** completed tests %s: **%.1f%%** were authenticated within 24 hours of sample collection and **%.1f%%** within 48 hours. "
                       "Average turnaround: **%.1f hours** (collection to authenticated report). This measures actual elapsed time, not each test's individual promised TAT."
                % (format(n, ","), _label(p), w24 * 100.0 / n, w48 * 100.0 / n, avg / 60.0), suggestions=["Which tests are delayed?"])


def _invoices(Q, org):
    rows = Q("SELECT TOP 4 INVOICENO, INVOICENODT, FromDate, ToDate, TotAmt, PaidAmt, DueAmt FROM trnInvoiceGeneration WHERE ORGCODE = ? ORDER BY INVOICENODT DESC", (org,))
    if not rows:
        return _out("invoice", "No invoice has been generated for your account yet.")
    r = rows[0]
    return _out("invoice", "Your latest invoice is **%s** dated **%s** (%s to %s) for **%s**; due **%s**." % (r[0], _d(r[1]), _d(r[2]), _d(r[3]), _inr(r[4]), _inr(r[6])),
                _tbl("Latest invoices", ["Invoice", "Date", "Period", "Amount", "Paid", "Due"],
                     [[x[0], _d(x[1]), "%s to %s" % (_d(x[2]), _d(x[3])), _inr(x[4]), _inr(x[5]), _inr(x[6])] for x in rows]), suggestions=["Request invoice copy"])


def _due_date(Q, org):
    o = Q("SELECT TOP 1 CREDITPERIOD FROM mstOrganisation WHERE ORGANISATIONCODE = ?", (org,))
    per = o[0][0] if o else None
    m = re.search(r"\d+", str(per or ""))
    days = int(m.group(0)) if m else None
    inv = Q("SELECT TOP 1 INVOICENO, INVOICENODT, DueAmt FROM trnInvoiceGeneration WHERE ORGCODE = ? AND ISNULL(DueAmt,0) > 0 ORDER BY INVOICENODT ASC", (org,))
    if not inv:
        return _out("due", "I see no unpaid invoice on your account right now.")
    no, dt, due = inv[0]
    if days is None:
        return _out("due", "Oldest unpaid invoice is **%s** dated **%s** with **%s** due. Your credit period is not recorded, so I cannot compute the due date." % (no, _d(dt), _inr(due)))
    try:
        d0 = date.fromisoformat(_d(dt))
        return _out("due", "Oldest unpaid invoice **%s** (%s): **%s** due by **%s** (invoice date + %d credit days)." % (no, _d(dt), _inr(due), (d0 + timedelta(days=days)).isoformat(), days),
                    suggestions=["Billing statement"])
    except Exception:
        return None


def _patient_count(Q, org, p):
    a, b = _dates(p)
    r = Q("SELECT COUNT(DISTINCT pr.BILLNO), COUNT(DISTINCT ISNULL(NULLIF(pr.UHID,''), pr.Name)) FROM trnINVLABPRI pr "
          "WHERE pr.ORGANISATIONCODE = ? AND pr.BILLDATE >= ? AND pr.BILLDATE < ?", (org, a, b))
    bills, pats = (int(r[0][0] or 0), int(r[0][1] or 0)) if r else (0, 0)
    s = _status_for_period(Q, org, p)
    return _out("patient_count", "Your organisation had **%s patients** (%s bills) %s. %s" % (format(pats, ","), format(bills, ","), _label(p), s.get("answer", "")),
                s.get("table"), suggestions=["Which tests are still pending?"])


def route2(Q, org, q, p, bill):
    has_per = bool(re.search(r"today|yesterday|week|month|quarter|20\d\d", q))
    if re.search(r"\bstatement|ledger\b", q):
        return None                      # handled by the account answers
    if re.search(r"\b(unpaid|pending|due|outstanding) invoices?\b|\binvoices? (are |that are |which are )?(unpaid|pending|due)\b", q):
        return _invoices(Q, org)
    if re.search(r"\bhow many (invoices|bills)\b", q) and not bill and not re.search(r"\bpending|unpaid|due\b", q):
        return _billing_total(Q, org, p)
    if re.search(r"\b(delayed|overdue|likely to be delayed|running late|beyond tat|crossed tat|late reports?)\b", q) and not re.search(r"\b(complain|raise|register|escalate)\b", q):
        return _delayed(Q, org)
    if re.search(r"\bhow many\b.*\b(patients?|people|persons?|employees|staff|customers|walk-?ins?|visits?)\b", q) and not bill:
        return _patient_count(Q, org, p)
    if re.search(r"\bhow many\b.*\b(reports?|tests?|orders?)\b.*\b(pending|not ready|outstanding|waiting)\b|\b(pending|waiting)\b.*\bhow many\b", q) and not bill:
        return _status_for_period(Q, org, p)
    if re.search(r"\b(which|list|show|what)\b.*\b(tests?|reports?|orders?|samples?)\b.*\b(pending|not (yet )?(ready|completed|done)|under processing|in process|still)\b|\b(pending|still pending)\b.*\b(list|tests|which)\b", q) \
            and not bill:
        return _pending_list(Q, org, p)
    if re.search(r"\b(rejection|rejected)\b.*\b(percent|percentage|rate|%|ratio)\b|\b(percent|percentage|rate|ratio)\b.*\b(rejection|rejected)\b", q):
        return _rejection(Q, org, p)
    if re.search(r"\b(most|top|frequent|frequently|popular|highest)\b.*\b(ordered|tests?|requested|booked)\b|\bwhich tests were\b", q) and re.search(r"\btests?\b", q) and not re.search(r"\bbranch|location|lab\b", q):
        return _top_tests(Q, org, p)
    if re.search(r"\b(which|what|top|highest|busiest)\b.*\b(branch|location|centre|center)\b.*\b(volume|most|highest|orders|tests|bills|busiest)\b|\b(branch|location)[- ]?wise\b", q):
        return _branch_volume(Q, org, p)
    if re.search(r"\b(trend|quarter|last (three|3) months|compare|comparison|month[- ]on[- ]month|growth)\b", q) and re.search(r"\b(volume|invoices?|billing|billed|orders|tests|bills|revenue)\b", q):
        return _trend(Q, org)
    if re.search(r"\b(tat|turnaround)\b.*\b(performance|percent|percentage|met|compliance|average|avg)\b|\b(percent|percentage)\b.*\b(tat|on time|within)\b|\bon[- ]time\b", q) and re.search(r"\b(report|reports|tat|tests?)\b", q):
        return _tat_performance(Q, org, p)
    if re.search(r"\b(invoice|invoices)\b.*\b(generated|raised|issued|created|ready)\b|\bhas our (monthly )?invoice\b", q):
        return _invoices(Q, org)
    if re.search(r"\b(when|date)\b.*\b(next )?(payment|dues?|due)\b.*\b(due|date|payable|pay)?\b|\bdue date\b|\bnext payment\b|\bpayment due\b", q) and not re.search(r"\b(has|have|received|paid)\b", q):
        return _due_date(Q, org)
    if re.search(r"\b(monthly )?(billing|billed) total\b|\btotal (billing|billed)\b|\brevenue summary\b|\bhow much (have we|did we) (billed|bill|order)\b|\bmonthly billing\b", q):
        return _billing_total(Q, org, p)
    if re.search(r"\b(pending[- ]order|order summary|pending summary|operational summary|orders? (status|summary))\b", q):
        return _status_for_period(Q, org, p if has_per else "today")
    return None
