import types
from agent import guardian as g

def test_read_only_guard():
    ok = lambda q: g.is_safe_select(q)[0]
    assert ok("SELECT TOP 5 * FROM trnINVLABPRI")
    assert ok("WITH a AS (SELECT 1 x) SELECT * FROM a")
    assert ok("SELECT NAME FROM mst WHERE NAME = 'drop table x'")
    for bad in ("SELECT 1; DROP TABLE x", "SELECT * INTO #t FROM a", "UPDATE a SET b=1",
                "select 1\nexec sp_who", "SELECT * FROM OPENROWSET('x')", "", "DELETE FROM a"):
        assert not ok(bad), bad

def test_classify_and_redact():
    assert g.classify("Invalid column name 'TOTALAMOUNT'")["category"] == "schema_changed"
    assert g.classify("Login failed for user")["category"] == "database_connection"
    assert g.classify("zzz")["category"] == "unknown"
    assert "secret" not in g.record_event("T1", "ask", "PWD=secret;UID=sa")["error"]

def test_circuit_breaker_isolated():
    calls = {"n": 0}
    m = types.SimpleNamespace()
    def fake(db_name=None, *a, **k):
        calls["n"] += 1
        return None
    m.get_hospital_connection = fake
    g.install(m)
    for _ in range(g.FAIL_LIMIT):
        m.get_hospital_connection("BAD_DB")
    n = calls["n"]
    assert g.circuit_open("BAD_DB") and m.get_hospital_connection("BAD_DB") is None and calls["n"] == n
    m.get_hospital_connection("GOOD_DB"); assert calls["n"] == n + 1 and not g.circuit_open("GOOD_DB")
