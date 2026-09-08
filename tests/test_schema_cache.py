from unittest.mock import patch

from agent.tools import describe_table, run_sql_query, reset_request_schema_cache


class _FakeCursor:
    def __init__(self, call_log):
        self._call_log = call_log

    def execute(self, q, params=None):
        if "INFORMATION_SCHEMA" in q:
            self._call_log.append(params)
        self.last_params = params

    def fetchall(self):
        if self.last_params and "trninvlabdet" in str(self.last_params).lower():
            return [("DEPTCODE", "varchar"), ("BILLDATE", "date")]
        return []

    @property
    def description(self):
        return [("DEPTCODE",)]

    def fetchmany(self, n):
        return [("9",)]


class _FakeConn:
    def __init__(self, call_log):
        self._call_log = call_log

    def cursor(self):
        return _FakeCursor(self._call_log)

    def close(self):
        pass


def test_run_sql_query_reuses_describe_table_cache_no_extra_db_call():
    # This is the actual latency fix: run_sql_query's column validator
    # used to always hit INFORMATION_SCHEMA once per referenced table,
    # even when describe_table had just fetched the exact same columns
    # seconds earlier in the same conversation — a real, measurable,
    # avoidable database round-trip on every single query.
    call_log = []
    reset_request_schema_cache()
    with patch("agent.tools.get_hospital_connection", return_value=_FakeConn(call_log)):
        describe_table.invoke({"table_name": "trninvlabdet", "role": "admin"})
        calls_after_describe = len(call_log)

        run_sql_query.invoke({
            "query": "SELECT trninvlabdet.DEPTCODE FROM trninvlabdet WHERE trninvlabdet.DEPTCODE = 9",
            "role": "admin",
        })
        calls_after_query = len(call_log)

    assert calls_after_query == calls_after_describe, (
        f"expected no extra INFORMATION_SCHEMA call, went from {calls_after_describe} to {calls_after_query}"
    )


def test_validation_still_rejects_invalid_columns_after_caching_change():
    # The whole point of this feature is catching wrong-column guesses
    # before execution — confirm the caching optimization didn't
    # silently weaken that.
    call_log = []
    reset_request_schema_cache()
    with patch("agent.tools.get_hospital_connection", return_value=_FakeConn(call_log)):
        describe_table.invoke({"table_name": "trninvlabdet", "role": "admin"})
        result = run_sql_query.invoke({
            "query": "SELECT trninvlabdet.NOTAREALCOLUMN FROM trninvlabdet",
            "role": "admin",
        })
    assert "rejected" in result.lower()
    assert "NOTAREALCOLUMN" in result


def test_validation_still_allows_real_columns_after_caching_change():
    call_log = []
    reset_request_schema_cache()
    with patch("agent.tools.get_hospital_connection", return_value=_FakeConn(call_log)):
        describe_table.invoke({"table_name": "trninvlabdet", "role": "admin"})
        result = run_sql_query.invoke({
            "query": "SELECT trninvlabdet.DEPTCODE FROM trninvlabdet",
            "role": "admin",
        })
    assert "rejected" not in result.lower()


def test_reset_clears_stale_cache_between_requests():
    # Simulates a worker thread reused across two different, unrelated
    # requests — without a reset, the second request could silently
    # reuse cached columns that belong to a different query/table.
    call_log = []
    reset_request_schema_cache()
    with patch("agent.tools.get_hospital_connection", return_value=_FakeConn(call_log)):
        describe_table.invoke({"table_name": "trninvlabdet", "role": "admin"})
        calls_before_reset = len(call_log)

        reset_request_schema_cache()  # simulates a new request starting

        describe_table.invoke({"table_name": "trninvlabdet", "role": "admin"})
        calls_after_reset = len(call_log)

    assert calls_after_reset > calls_before_reset, "reset should force a fresh lookup, not reuse the old cache"