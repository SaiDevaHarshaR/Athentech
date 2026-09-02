import json
from unittest.mock import patch

import auth.table_relationships as rel_mod
from auth.roles import Role
from reports.patient_report_generator import (
    find_patient, gather_patient_data, generate_structured_report,
    build_patient_report_data, PatientNotFound, PatientAmbiguous,
    _find_column, _parse_llm_json,
)


class _FakeCursor:
    def __init__(self, conn):
        self.conn = conn
        self.description = [("ID",), ("PatientID",), ("Amount",), ("PaymentMode",)]

    def execute(self, query, params=None):
        if "INFORMATION_SCHEMA.COLUMNS" in query:
            self._r = [("ID",), ("UHID",), ("PatientName",), ("Age",), ("DOB",), ("Gender",), ("RegDate",)]
        elif "LIKE" in query:
            self._r = self.conn.name_rows
        elif "mstpatientregistration" in query.lower():
            self._r = self.conn.uhid_rows
        else:
            self._r = self.conn.related_rows or []

    def fetchall(self):
        return self._r


class _FakeConn:
    def __init__(self, uhid_rows=None, name_rows=None, related_rows=None):
        self.uhid_rows = uhid_rows or []
        self.name_rows = name_rows or []
        self.related_rows = related_rows

    def cursor(self):
        return _FakeCursor(self)

    def close(self):
        pass


class _FakeLLM:
    def __init__(self, response_text):
        self.response_text = response_text
        self.last_prompt = None

    def invoke(self, prompt):
        self.last_prompt = prompt
        class R:
            content = self.response_text
        return R()


def test_find_column_matches_by_keyword():
    columns = ["ID", "UHID", "PatientName", "DOB", "Gender", "HospitalName"]
    assert _find_column(columns, ["uhid"]) == "UHID"
    assert _find_column(columns, ["name"], exclude=["hospname", "hospitalname"]) == "PatientName"


def test_parse_llm_json_handles_markdown_fences():
    assert _parse_llm_json('```json\n{"a": 1}\n```') == {"a": 1}


def test_find_patient_by_uhid():
    conn = _FakeConn(uhid_rows=[(1, "KDX26929648", "DEVANSH", 3, None, "M", "2026-08-28")])
    with patch("reports.patient_report_generator.get_hospital_connection", return_value=conn):
        result = find_patient("KDX26929648", "testdb")
    assert result["name"] == "DEVANSH"
    assert result["age"] == 3


def test_find_patient_ambiguous_name_raises_with_candidates():
    conn = _FakeConn(name_rows=[
        (2, "KDX1", "JOHN", 30, None, "M", "2026-01-01"),
        (3, "KDX2", "JOHN", 40, None, "M", "2026-01-02"),
    ])
    with patch("reports.patient_report_generator.get_hospital_connection", return_value=conn):
        try:
            find_patient("JOHN", "testdb")
            assert False, "should have raised"
        except PatientAmbiguous as e:
            assert len(e.candidates) == 2


def test_find_patient_not_found_raises():
    conn = _FakeConn()
    with patch("reports.patient_report_generator.get_hospital_connection", return_value=conn):
        try:
            find_patient("NOBODY", "testdb")
            assert False, "should have raised"
        except PatientNotFound:
            pass


def test_gather_patient_data_uses_relationships_and_respects_role(monkeypatch):
    monkeypatch.setitem(rel_mod.REAL_TABLE_RELATIONSHIPS, "trninvoicepayments",
                         [("PatientID", "mstpatientregistration", "ID")])
    conn = _FakeConn(related_rows=[(1, 42, 500, "Cash")])

    with patch("reports.patient_report_generator.get_hospital_connection", return_value=conn), \
         patch("reports.patient_report_generator.REAL_TABLE_TO_CATEGORY", {"trninvoicepayments": "billing"}):
        result_admin = gather_patient_data(42, "testdb", Role.ADMIN)
        # Reception was intentionally given billing access in a recent
        # policy update (front-desk staff typically handle payments) —
        # viewer is the role that still has no billing access, use that
        # to test the "role without access" case instead.
        result_viewer = gather_patient_data(42, "testdb", Role.VIEWER)

    assert "trninvoicepayments" in result_admin
    assert result_admin["trninvoicepayments"][0]["Amount"] == 500
    assert "trninvoicepayments" not in result_viewer  # viewer has no billing access


def test_generate_structured_report_stays_honest_with_no_data():
    llm = _FakeLLM(json.dumps({
        "patient_name": "DEVANSH", "patient_age": 3, "patient_gender": "M",
        "health_score": "-no_data", "health_summary": "Only demographic information was available.",
        "priority_findings": [], "all_findings": [], "health_connections": [], "trends": [],
        "action_plan": {"doctor": "", "food": "", "activity": "", "followup": ""},
    }))
    result = generate_structured_report(
        {"name": "DEVANSH", "age": 3, "gender": "M", "uhid": "KDX26929648"}, {}, "Test Hospital", llm
    )
    assert result["all_findings"] == []
    assert "demographic" in result["health_summary"].lower()
    # the grounding instruction must actually be in the prompt sent to the LLM
    assert "do not invent findings" in llm.last_prompt.lower()


def test_generate_structured_report_handles_malformed_llm_response():
    llm = _FakeLLM("this is not valid json at all")
    result = generate_structured_report({"name": "SWATHI", "age": 32, "gender": "F"}, {}, "Test Hospital", llm)
    assert result["patient_name"] == "SWATHI"
    assert "could not generate" in result["health_summary"].lower()


def test_generate_structured_report_handles_real_datetime_in_patient_info():
    # Real bug found in production: patient_info can contain a real
    # datetime object (from a DATE/DATETIME database column, e.g. DOB or
    # registration_date) — json.dumps() without default=str crashes on
    # that. Reproduces the exact crash scenario from the traceback.
    from datetime import datetime
    llm = _FakeLLM(json.dumps({
        "patient_name": "DEVANSH", "patient_age": 3, "patient_gender": "M",
        "health_score": "-no_data", "health_summary": "test",
        "priority_findings": [], "all_findings": [], "health_connections": [], "trends": [],
        "action_plan": {"doctor": "", "food": "", "activity": "", "followup": ""},
    }))
    patient_info = {
        "patient_id": 1, "uhid": "KDX26929648", "name": "DEVANSH",
        "age": 3, "dob": datetime(2023, 5, 1), "gender": "M",
        "registration_date": datetime(2026, 8, 28, 14, 30, 0),
    }
    result = generate_structured_report(patient_info, {}, "Test Hospital", llm)
    assert result["patient_name"] == "DEVANSH"


def test_build_patient_report_data_full_pipeline():
    conn = _FakeConn(uhid_rows=[(1, "KDX26929648", "DEVANSH", 3, None, "M", "2026-08-28")])
    llm = _FakeLLM(json.dumps({
        "patient_name": "DEVANSH", "patient_age": 3, "patient_gender": "M",
        "health_score": "-no_data", "health_summary": "Only demographic information was available.",
        "priority_findings": [], "all_findings": [], "health_connections": [], "trends": [],
        "action_plan": {"doctor": "", "food": "", "activity": "", "followup": ""},
    }))
    with patch("reports.patient_report_generator.get_hospital_connection", return_value=conn):
        result = build_patient_report_data("KDX26929648", "testdb", "admin", "Test Hospital", llm)

    assert result["patient_name"] == "DEVANSH"
    assert result["hospital_name"] == "Test Hospital"