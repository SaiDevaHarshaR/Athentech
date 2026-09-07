from unittest.mock import patch

from reports.curated_queries import resolve_location_id, get_day_collection
from agent.tools import get_verified_day_collection


class _FakeCursor:
    def __init__(self, conn):
        self.conn = conn

    def execute(self, q, params=None):
        self.last_query = q
        self._r = self.conn.location_rows if "mstlocationusers" in q else self.conn.collection_rows

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


def test_no_location_match_returns_clean_error():
    conn = _FakeConn(location_rows=[])
    with patch("reports.curated_queries.get_hospital_connection", return_value=conn):
        result = get_day_collection("Nonexistent", "2026-09-07", "2026-09-07", "TestDB")
    assert "error" in result


def test_genuine_no_data_is_distinguishable_from_errors():
    conn = _FakeConn(location_rows=[(3087, "Kompally")], collection_rows=[])
    with patch("reports.curated_queries.get_hospital_connection", return_value=conn):
        result = get_day_collection("Kompally", "2026-09-07", "2026-09-07", "TestDB")
    assert result.get("no_data") is True
    assert "error" not in result


def test_invalid_date_format_rejected_before_any_query():
    result = get_day_collection("Kompally", "not-a-date", "2026-09-07", "TestDB")
    assert "error" in result


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