from unittest.mock import patch

from reports.curated_queries import resolve_location_id, get_day_collection, resolve_relative_date
from agent.tools import get_verified_day_collection


class _FakeCursor:
    def __init__(self, conn):
        self.conn = conn

    def execute(self, q, params=None):
        self.last_query = q
        self._r = self.conn.location_rows if "trntempdaycollall" in q else self.conn.collection_rows

    def fetchall(self):
        return self._r


class _FakeConn:
    def __init__(self, location_rows, collection_rows=None):
        self.location_rows = location_rows
        self.collection_rows = collection_rows or []

    def cursor(self):
        return _FakeCursor(self)

    def close(self):
        pass


def test_unique_location_match_returns_real_breakdown():
    conn = _FakeConn(location_rows=[(3087, "Kompally")], collection_rows=[("Cash", 5000.0), ("UPI", 3000.0)])
    with patch("reports.curated_queries.get_hospital_connection", return_value=conn):
        result = get_day_collection("Kompally", "2026-09-07", "2026-09-07", "TestDB")
    assert result["total"] == 8000.0
    assert result["location"] == "Kompally"
    assert len(result["breakdown"]) == 2


def test_ambiguous_location_is_flagged_not_silently_picked():
    conn = _FakeConn(location_rows=[(1, "Kompally Main"), (2, "Kompally Fetal Medicine")])
    with patch("reports.curated_queries.get_hospital_connection", return_value=conn):
        result = get_day_collection("Kompally", "2026-09-07", "2026-09-07", "TestDB")
    assert result["ambiguous"] is True
    assert len(result["candidates"]) == 2


def test_exact_match_preferred_over_ambiguity():
    # Real gap found in production: "Kukatpally" matched both
    # "Kukatpally" and "Spinova-Kukatpally" via LIKE, forcing an
    # unnecessary clarifying question even though one candidate was an
    # exact match to what was actually said.
    conn = _FakeConn(location_rows=[("LOC01", "Kukatpally"), ("LOC02", "Spinova-Kukatpally")])
    with patch("reports.curated_queries.get_hospital_connection", return_value=conn):
        result = get_day_collection("Kukatpally", "2026-09-01", "2026-09-07", "TestDB")
    assert result.get("ambiguous") is not True
    assert result["location"] == "Kukatpally"
    assert result["location_id"] == "LOC01"


def test_genuine_ambiguity_still_asks_when_no_exact_match():
    conn = _FakeConn(location_rows=[("LOC04", "Kompally Fetal Medicine"), ("LOC07", "Srikara-Kompally")])
    with patch("reports.curated_queries.get_hospital_connection", return_value=conn):
        result = get_day_collection("Kompally", "2026-09-01", "2026-09-07", "TestDB")
    assert result["ambiguous"] is True


def test_no_location_match_returns_clean_error():
    conn = _FakeConn(location_rows=[])
    with patch("reports.curated_queries.get_hospital_connection", return_value=conn):
        result = get_day_collection("Nonexistent", "2026-09-07", "2026-09-07", "TestDB")
    assert "error" in result


def test_null_paidamount_distinguished_from_real_zero():
    # Real finding: a matching row can exist with SUM(PAIDAMOUNT) = NULL
    # (bills/transactions exist, but the amount wasn't recorded as a
    # number) — silently treating that the same as a real 0 hides what's
    # actually happening. NULL comes back as None from the DB driver.
    conn = _FakeConn(location_rows=[(3087, "Srikara-Kompally")], collection_rows=[("Cash", None)])
    with patch("reports.curated_queries.get_hospital_connection", return_value=conn):
        result = get_day_collection("Srikara-Kompally", "2026-09-01", "2026-09-07", "TestDB")
    assert result["had_null_amounts"] is True
    assert result["total"] == 0.0  # still displays as 0 for the total, but the flag distinguishes why


def test_real_zero_amount_not_flagged_as_null():
    conn = _FakeConn(location_rows=[(3087, "Srikara-Kompally")], collection_rows=[("Cash", 0.0)])
    with patch("reports.curated_queries.get_hospital_connection", return_value=conn):
        result = get_day_collection("Srikara-Kompally", "2026-09-01", "2026-09-07", "TestDB")
    assert result["had_null_amounts"] is False


def test_genuine_no_data_is_distinguishable_from_errors():
    conn = _FakeConn(location_rows=[(3087, "Kompally")], collection_rows=[])
    with patch("reports.curated_queries.get_hospital_connection", return_value=conn):
        result = get_day_collection("Kompally", "2026-09-07", "2026-09-07", "TestDB")
    assert result.get("no_data") is True
    assert "error" not in result


def test_invalid_date_format_rejected_before_any_query():
    result = get_day_collection("Kompally", "not-a-date", "2026-09-07", "TestDB")
    assert "error" in result


def test_relative_date_keywords_resolve_to_real_current_date():
    # Regression test for a real production bug: when the LLM was asked
    # to compute "yesterday" as a literal date itself, it produced
    # 2023-10-06 — years in the past, using its own stale internal
    # sense of "today" rather than the real date. This confirms the
    # fix: "yesterday" now resolves using the real server clock, not
    # anything the caller (LLM or otherwise) computed.
    from datetime import date, timedelta
    today = date.today()
    assert resolve_relative_date("today") == today.isoformat()
    assert resolve_relative_date("yesterday") == (today - timedelta(days=1)).isoformat()
    assert resolve_relative_date("yesterday") != "2023-10-06"


def test_get_day_collection_accepts_relative_keywords_directly():
    conn = _FakeConn(location_rows=[(3087, "Kompally")], collection_rows=[("Cash", 5000.0)])
    with patch("reports.curated_queries.get_hospital_connection", return_value=conn):
        # Caller passes "today"/"yesterday" literally, exactly as the
        # LLM is now instructed to — no date math required or trusted
        # from the caller.
        result = get_day_collection("Kompally", "yesterday", "today", "TestDB")
    assert "error" not in result
    assert result["total"] == 5000.0


def test_tool_enforces_role_restriction():
    result = get_verified_day_collection.invoke({
        "location_keyword": "Kompally", "date_from": "2026-09-07", "date_to": "2026-09-07", "role": "lab_tech"
    })
    assert "does not have access" in result


def test_tool_formats_real_result_readably():
    conn = _FakeConn(location_rows=[(3087, "Kompally")], collection_rows=[("Cash", 5000.0)])
    with patch("reports.curated_queries.get_hospital_connection", return_value=conn):
        result = get_verified_day_collection.invoke({
            "location_keyword": "Kompally", "date_from": "2026-09-07", "date_to": "2026-09-07", "role": "admin"
        })
    assert "Kompally" in result
    assert "5000" in result


def test_tool_surfaces_ambiguity_as_a_question_not_a_guess():
    conn = _FakeConn(location_rows=[(1, "Kompally Main"), (2, "Kompally Fetal Medicine")])
    with patch("reports.curated_queries.get_hospital_connection", return_value=conn):
        result = get_verified_day_collection.invoke({
            "location_keyword": "Kompally", "date_from": "2026-09-07", "date_to": "2026-09-07", "role": "admin"
        })
    assert "Multiple locations match" in result
    assert "Kompally Main" in result and "Kompally Fetal Medicine" in result