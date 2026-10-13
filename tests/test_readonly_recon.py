"""Day-collection reconciliation: never writes to the client DB, and the AMOUNTS follow the real procedure's formula."""
import pathlib
import re
import sys
import types

if "pyodbc" not in sys.modules:
    try:
        import pyodbc  # noqa: F401
    except Exception:
        sys.modules["pyodbc"] = types.ModuleType("pyodbc")

import reports.day_collection_reconciliation as R
import reports.day_collection_readonly as RO

# value returned by each sub-query, identified by a distinctive fragment of its SQL
VALUES = [
    ("SUM(ISNULL(B.TOTALAMOUNT,0)) + ISNULL(( SELECT", 10000),                                  # TOTALCASH
    ("dbo.DUEREC", 1200),                                                                      # TOTALDUES
    ("A.PAYTYPE = 'COMPANY' AND A.CREDITBILL = 'True'", 700),                                  # TOTALCREDITS
    ("SUM(ISNULL(A.CONCESSIONAMOUNT,0))", 300),
    ("A.TYPE IN ('OPLAB','DUE PAYMENT') AND A.MODE IN ('CREDITCARD')", 1000),                  # credit cards
    ("A.TYPE IN ('OPLAB','DUE PAYMENT') AND A.MODE IN ('CHEQUE')", 400),
    ("A.TYPE IN ('OPLAB','DUE PAYMENT') AND A.MODE IN ('DD','UPI','ONLINE')", 600),
    ("A.STATUS = 'R' AND A.PREVIOUSBILLNO = B.BILLNO AND CONVERT(DATE, B.BILLDATE, 106) = ?", 200),   # refunds today
    ("CONVERT(DATE, B.BILLDATE, 101) < CONVERT(DATE, ?, 23)", 100),                                        # refunds from earlier bills
    ("trnVoucherGen", 50),                                                                      # expenditure
    ("A.TYPE IN ('DUE PAYMENT') AND A.LOCATIONID = ? AND A.PREVIOUSBILLNO = B.BILLNO AND A.STATUS = 'P' AND CONVERT(DATE, B.BILLDATE, 106) < ? AND A.MODE IN ('CASH')", 800),
    ("A.MODE IN ('UPI','ONLINE')", 150),                                                        # previous dues via UPI
    ("B.TYPE = 'OPLAB'", 12345),                                                                # gross total credits
    ("COUNT(*) FROM trnINVLABPRI A", 42),
    ("B.MODE IN ('CASH')", 125),                 # corporate advance cash
    ("B.MODE IN ('Credit Card')", 75),          # corporate advance credit card
    ("B.MODE IN ('Cheque')", 25),               # corporate advance cheque
    ("B.MODE IN ('UPI')", 40),                  # corporate advance upi
    ("B.MODE IN ('APP')", 5),                   # corporate advance app
    ("B.MODE IN ('RTGS', 'RTGS/NEFT')", 10),    # corporate advance rtgs

]


class Cur:
    def __init__(self, log, fail_dues=False):
        self.log, self.fail_dues, self.description, self._v = log, fail_dues, None, 0
    def execute(self, sql, params=None):
        self.log.append(sql)
        sql = re.sub(r"\s+", " ", sql)
        if "mstLocation" in sql:
            self._rows = [("LOC1", "Main")]; return self
        if "dbo.DUEREC" in sql and self.fail_dues:
            raise RuntimeError("Invalid object name 'dbo.DUEREC'")
        self._rows = None
        self._v = 0
        if "trnCompPayments B" in sql:
            modes = tuple(params[1:-1])
            self._v = {("CASH",): 125, ("Credit Card",): 75,
                       ("Cheque",): 25, ("UPI",): 40,
                       ("APP",): 5, ("RTGS", "RTGS/NEFT"): 10}.get(modes, 0)
            return self
        for frag, val in VALUES:
            if frag in sql:
                self._v = val
                break
        return self
    def fetchall(self): return self._rows
    def fetchone(self): return (self._v,)


class Conn:
    def __init__(self, log, fail_dues=False): self.log, self.fail_dues = log, fail_dues
    def cursor(self): return Cur(self.log, self.fail_dues)
    def close(self): pass


def test_amounts_follow_real_formula_including_dues(monkeypatch):
    log = []
    monkeypatch.setattr(RO, "get_hospital_connection", lambda *a, **k: Conn(log))
    r = R.get_day_collection_all_branches("2026-10-12", "db")
    b = r["branches"][0]
    assert b["TOTALDUES"] == 1200 and b["TOTALBILLS"] == 42
    # core = cash - dues - concessions - cc - cheque - upi - refunds - prev refunds - expenditure
    assert b["TOTALCOREBUSINESSCASH"] == 10000 - 1200 - 300 - 1000 - 400 - 600 - 200 - 100 - 50
    assert b["TOTALCASHINHAND"] == b["TOTALCOREBUSINESSCASH"] + 800 + 125
    assert b["COMPADVCASH"] == 125
    assert b["TOTALCCINHAND"] == b["TOTALCCRECEIVED"] + 75
    assert b["TOTALCHQONLINEUPI"] == b["TOTALONLINEUPI"]
    assert b["TOTALONLINEUPIINHAND"] == b["TOTALUPI"] + b["PREVDUE_DD"] + b["PREVDUE_UPI"] + b["COMPADVUPI"]
    assert b["TOTALCHQINHAND"] == b["TOTALCHEQUE"] + b["PREVDUE_CHEQUE"] + b["COMPADVCHQ"]
    assert len([k for k in R._COLUMNS if k in b]) == 32 + 2  # full financial fields + LOCATIONID + LOCATION

    assert not any("EXEC" in q.upper() for q in log)


def test_missing_due_functions_fail_visibly_not_silently(monkeypatch):
    monkeypatch.setattr(RO, "get_hospital_connection", lambda *a, **k: Conn([], fail_dues=True))
    r = R.get_day_collection_all_branches("2026-10-12", "db")
    assert "error" in r and "Dues could not be calculated" in r["error"] and "branches" not in r


def test_one_branch_path_is_read_only_too(monkeypatch):
    log = []
    monkeypatch.setattr(RO, "get_hospital_connection", lambda *a, **k: Conn(log))
    one = R.get_day_collection_one_branch("main", "2026-10-12", "db")
    assert one["branch"]["LOCATION"] == "Main" and not any("EXEC" in q.upper() for q in log)


def test_no_switch_re_enables_the_writing_procedure(monkeypatch):
    monkeypatch.setenv("ALLOW_SP_WRITE_RECON", "1")
    log = []
    monkeypatch.setattr(RO, "get_hospital_connection", lambda *a, **k: Conn(log))
    R.get_day_collection_all_branches("2026-10-12", "db")
    assert not any("EXEC" in q.upper() for q in log)


def test_no_unexpected_stored_procedure_calls_in_service_code():
    root = pathlib.Path(__file__).resolve().parents[1]
    allowed = {"reports/lab_day_collection.py"}      # dbo.LabDayCollection: confirmed SELECT-only in its source
    found = set()
    for d in ("agent", "reports"):
        for f in (root / d).rglob("*.py"):
            if re.search(r'["\']\s*EXEC\s+dbo\.', f.read_text(encoding="utf-8", errors="ignore")):
                found.add(f.relative_to(root).as_posix())
    assert found <= allowed, f"new EXEC usage needs review: {found - allowed}"


def test_parity_tool_flags_differences():
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
    from tools.verify_recon_parity import compare, COLS
    assert len(COLS) == 32
    base = {c: 0 for c in COLS}
    original = dict(base, LOCATIONID="L1", TOTALCASHINHAND=100, TOTALDUES=5)
    same = dict(base, LOCATIONID="L1", TOTALCASHINHAND=100, TOTALDUES=5)
    mismatch = dict(base, LOCATIONID="L1", TOTALCASHINHAND=90, TOTALDUES=5)
    assert compare([original], [same]) == []
    assert any(d[1] == "TOTALCASHINHAND" for d in compare([original], [mismatch]))
    assert any(d[1] == "(reference)" for d in compare([], [same]))
    assert any(d[1] == "(branch)" for d in compare([original], [same, dict(same, LOCATIONID="L2")]))
    assert any(d[1] == "TOTALDUES" for d in compare([original], [{k:v for k,v in same.items() if k != "TOTALDUES"}]))


def test_parity_tool_never_executes_writing_sp():
    src = (pathlib.Path(__file__).resolve().parents[1] / "tools/verify_recon_parity.py").read_text()
    # This is a text-level regression guard. Real safety additionally comes from DB read-only credentials.
    assert 'cur.execute("EXEC' not in src
    assert 'cur.execute("DELETE' not in src
    assert 'conn.rollback()' not in src
    assert 'get_day_collection_all_branches_readonly' in src


def test_reference_csv_requires_all_32_fields(tmp_path):
    from tools.verify_recon_parity import _reference_csv
    import pytest
    p = tmp_path / "incomplete.csv"
    p.write_text("LOCATIONID,TOTALCASHINHAND\nL1,100\n")
    with pytest.raises(ValueError, match="missing fields"):
        _reference_csv(p)
