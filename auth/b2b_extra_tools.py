"""Extra READ-ONLY tools for the B2B AI agent (patch166): date-range billing, invoices in a range, overdue invoices,
billing by test, and which packages contain a test. Every query is a SELECT bound to the verified organisation code."""
import re
from datetime import date, timedelta

_SYN = {"thyroid": ["thyroid", "tsh", "thyroxine", "triiodo", "t3", "t4"], "vitamin d": ["vitamin d", "25-hydroxy", "25 hydroxy", "25-oh"],
        "vitamin b12": ["b12", "cobalamin"], "sugar": ["glucose", "hba1c", "glycosylated", "diabet"], "diabetes": ["glucose", "hba1c", "glycosylated", "diabet"],
        "cholesterol": ["lipid", "cholesterol"], "liver": ["liver", "lft", "sgot", "sgpt", "bilirubin"], "kidney": ["kidney", "renal", "kft", "creatinine", "urea"],
        "cbc": ["cbc", "complete blood"], "iron": ["iron", "ferritin", "tibc"], "calcium": ["calcium"], "urine": ["urine", "cue"]}


def make_extra(Q, org, done, A, A2):
    _out, _tbl, _inr, _d, _dates = A._out, A._tbl, A._inr, A._d, A._dates

    def _per(p):
        p = str(p or "").strip().lower().replace(" ", "_")
        return p if (p in ("today", "yesterday", "last_7_days", "this_month", "last_month") or re.fullmatch(r"last_\d{1,3}_days", p)) else "this_month"

    def _rng(s, e):
        try:
            a = date.fromisoformat(str(s).strip()[:10])
            es = str(e or "").strip().lower()
            b = date.today() if (not es or es in ("today", "now", "till today", "till now")) else date.fromisoformat(es[:10])
        except Exception:
            return None
        if b < a:
            a, b = b, a
        if (b - a).days > 400:
            a = b - timedelta(days=400)
        return a, b

    def billing_between(start_date: str, end_date: str = "today") -> str:
        """Number of bills, total billed amount and amount received between TWO dates (YYYY-MM-DD; end_date may be 'today'). Use for 'from September 2026 till today' (start 2026-09-01), 'between 5 Oct and 20 Oct', any custom range."""
        r = _rng(start_date, end_date)
        if not r:
            return "Give the dates as YYYY-MM-DD."
        a, b = r
        e = (b + timedelta(days=1)).isoformat()
        x = Q("SELECT COUNT(DISTINCT BILLNO), SUM(CAST(ISNULL(TOTALCHARGES,0) AS FLOAT)) FROM trnINVLABPRI WHERE ORGANISATIONCODE = ? AND BILLDATE >= ? AND BILLDATE < ?", (org, a.isoformat(), e))
        n, v = (int(x[0][0] or 0), float(x[0][1] or 0)) if x else (0, 0.0)
        rec = ""
        try:
            p = Q("SELECT SUM(CAST(ISNULL(PaidAmt,0) AS FLOAT)), COUNT(*) FROM trnCompPayments WHERE ORGCODE = ? AND Active = 1 AND PayDate >= ? AND PayDate < ?", (org, a.isoformat(), e))
            if p:
                rec = " Amount received in that period: **%s** (%d payments)." % (_inr(float(p[0][0] or 0)), int(p[0][1] or 0))
        except Exception:
            pass
        return done(_out("billing_total", "From **%s** to **%s** your organisation had **%s bills** with a billed total of **%s** (billed value, not cash).%s" % (a.isoformat(), b.isoformat(), format(n, ","), _inr(v), rec)))

    def invoices_between(start_date: str, end_date: str = "today") -> str:
        """The MONTHLY INVOICES the lab generated for this organisation between two dates (YYYY-MM-DD; end_date may be 'today'): how many, total, paid, due, with the list. Use for 'how many invoices from September till today'."""
        r = _rng(start_date, end_date)
        if not r:
            return "Give the dates as YYYY-MM-DD."
        a, b = r
        rows = Q("SELECT INVOICENO, INVOICENODT, FromDate, ToDate, TotAmt, PaidAmt, DueAmt FROM trnInvoiceGeneration WHERE ORGCODE = ? AND INVOICENODT >= ? AND INVOICENODT < ? ORDER BY INVOICENODT DESC",
                 (org, a.isoformat(), (b + timedelta(days=1)).isoformat()))
        if not rows:
            return done(_out("invoice", "No invoice was generated for your organisation between %s and %s." % (a.isoformat(), b.isoformat())))
        tot = sum(float(x[4] or 0) for x in rows); paid = sum(float(x[5] or 0) for x in rows); due = sum(float(x[6] or 0) for x in rows)
        return done(_out("invoice", "Between **%s** and **%s** the lab generated **%d invoice%s** for your organisation: total **%s**, paid **%s**, due **%s**." % (a.isoformat(), b.isoformat(), len(rows), "" if len(rows) == 1 else "s", _inr(tot), _inr(paid), _inr(due)),
                         _tbl("Invoices", ["Invoice", "Date", "Period", "Amount", "Paid", "Due"], [[x[0], _d(x[1]), "%s to %s" % (_d(x[2]), _d(x[3])), _inr(x[4]), _inr(x[5]), _inr(x[6])] for x in rows[:25]])))

    def overdue_invoices(min_days_overdue: int = 60) -> str:
        """Unpaid invoices of this organisation that are overdue by MORE than min_days_overdue days (overdue = today minus invoice date minus the credit period). Use for 'invoices overdue more than 60 days'."""
        try:
            md = max(0, min(int(min_days_overdue), 3650))
        except Exception:
            md = 60
        o = Q("SELECT TOP 1 CREDITPERIOD FROM mstOrganisation WHERE ORGANISATIONCODE = ?", (org,))
        m = re.search(r"\d+", str(o[0][0] if o else "") or "")
        cd = int(m.group(0)) if m else 0
        rows = Q("SELECT INVOICENO, INVOICENODT, TotAmt, PaidAmt, DueAmt FROM trnInvoiceGeneration WHERE ORGCODE = ? AND ISNULL(DueAmt,0) > 0 ORDER BY INVOICENODT", (org,))
        out = []
        for x in rows:
            try:
                od = (date.today() - date.fromisoformat(_d(x[1])) ).days - cd
            except Exception:
                continue
            if od > md:
                out.append([x[0], _d(x[1]), _inr(x[2]), _inr(x[4]), od])
        note = " (credit period %d days)" % cd if cd else " (no credit period recorded, counted from the invoice date)"
        if not out:
            return done(_out("due", "No unpaid invoice is overdue by more than %d days%s." % (md, note)))
        return done(_out("due", "**%d unpaid invoice%s** overdue by more than %d days%s." % (len(out), "" if len(out) == 1 else "s", md, note),
                         _tbl("Overdue invoices", ["Invoice", "Date", "Amount", "Due", "Days overdue"], out[:25])))

    def top_tests_by_billing(period: str = "last_month") -> str:
        """Tests that brought the HIGHEST BILLED AMOUNT (revenue / value, not count) for a period: today, yesterday, last_7_days, this_month, last_month, last_30_days, last_90_days."""
        p = _per(period)
        a, b = _dates(p)
        rows = Q("SELECT TOP 10 ISNULL(m.INVNAME, d.TCODE), COUNT(*), SUM(CAST(ISNULL(d.CHARGE,0) AS FLOAT)) FROM trnINVLABDET d JOIN trnINVLABPRI p ON p.BILLNO = d.BILLNO "
                 "LEFT JOIN mstInvestigations m ON m.INVCODE COLLATE DATABASE_DEFAULT = d.TCODE COLLATE DATABASE_DEFAULT WHERE p.ORGANISATIONCODE = ? AND p.BILLDATE >= ? AND p.BILLDATE < ? "
                 "GROUP BY ISNULL(m.INVNAME, d.TCODE) ORDER BY SUM(CAST(ISNULL(d.CHARGE,0) AS FLOAT)) DESC", (org, a, b))
        if not rows or float(rows[0][2] or 0) <= 0:
            return done(A2._top_tests(Q, org, p))        # no test-wise charges recorded: fall back to the count ranking
        return done(_out("top_tests", "Highest billed test %s: **%s** with **%s** across %s orders." % (A._label(p), rows[0][0], _inr(rows[0][2]), format(int(rows[0][1]), ",")),
                         _tbl("Tests by billed amount", ["Test", "Orders", "Billed amount"], [[r[0], r[1], _inr(r[2])] for r in rows])))

    def packages_with_test(test_name: str) -> str:
        """Which health packages / profiles of this organisation INCLUDE a given test or group (e.g. 'thyroid', 'vitamin D', 'lipid', 'HbA1c')."""
        w = re.sub(r"[^a-z0-9\- ]", " ", str(test_name or "").lower()).strip()
        if len(w) < 2:
            return "Which test? For example: thyroid, vitamin D, HbA1c."
        terms = None
        for k, v in _SYN.items():
            if k in w:
                terms = v; break
        terms = (terms or [w])[:6]
        cond = " OR ".join("LOWER(t.INVNAME) LIKE ?" for _ in terms)
        rows = Q("SELECT DISTINCT TOP 60 pk.INVCODE, pk.INVNAME FROM mstInvPackages p JOIN mstInvestigations t ON t.INVCODE COLLATE DATABASE_DEFAULT = p.TESTCODE COLLATE DATABASE_DEFAULT "
                 "JOIN mstInvestigations pk ON pk.INVCODE COLLATE DATABASE_DEFAULT = p.PACKAGECODE COLLATE DATABASE_DEFAULT WHERE p.ACTIVE = 1 AND pk.ACTIVE = 1 "
                 "AND (p.ORGCODE = ? OR ISNULL(p.ORGCODE,'') = '') AND (" + cond + ") ORDER BY pk.INVNAME", (org,) + tuple("%" + x + "%" for x in terms))
        if not rows:
            return done(_out("packages", "No package of your organisation includes a test matching \"%s\"." % w))
        return done(_out("packages", "**%d package%s** include a \"%s\" test." % (len(rows), "" if len(rows) == 1 else "s", w), _tbl("Packages", ["Package", "Code"], [[r[1], r[0]] for r in rows[:40]])))

    return [billing_between, invoices_between, overdue_invoices, top_tests_by_billing, packages_with_test]
