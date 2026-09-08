from unittest.mock import patch

from agent.schema_search import search_schema
from agent.tools import search_schema as search_schema_tool


def test_works_with_no_profile_at_all():
    # Must degrade gracefully when schema_profile.json hasn't been
    # generated yet — name/category matching alone should still work.
    with patch("agent.schema_search._load_profile", return_value={}):
        results = search_schema("patient registration")
    assert len(results) > 0
    assert any("patient" in r["table"] for r in results)


def test_substring_matching_finds_words_inside_concatenated_names():
    # Regression test for a real bug found while building this: table
    # names are one continuous string with no word separators (e.g.
    # "mstpatientregistration"), so naive token-set matching never finds
    # "patient" inside that string at all. Must use substring matching.
    with patch("agent.schema_search._load_profile", return_value={}):
        results = search_schema("patient registration")
    top = results[0]
    assert top["table"] == "mstpatientregistration"
    assert top["score"] > 0


def test_real_sample_value_match_is_the_strongest_signal():
    # This is the exact scenario that took hours to find manually in
    # production: searching "radiology" should surface mstdepartment
    # because its DEPARTMENTNAME column's real sample values literally
    # contain "Radiology" — a much stronger signal than the cryptic
    # table name alone.
    fake_profile = {
        "mstdepartment": {
            "table": "mstdepartment", "category": "labs",
            "columns": [{"column": "DEPARTMENTNAME", "sample_values": ["Radiology", "ENT", "Lab"]}],
        },
    }
    with patch("agent.schema_search._load_profile", return_value=fake_profile):
        results = search_schema("radiology")
    assert results[0]["table"] == "mstdepartment"
    assert "Radiology" in results[0]["why"]


def test_role_restriction_limits_results():
    with patch("agent.schema_search._load_profile", return_value={}):
        results = search_schema("patient registration", allowed_tables={"mstpatientregistration"})
    assert len(results) == 1
    assert results[0]["table"] == "mstpatientregistration"


def test_no_match_returns_empty_list_not_a_crash():
    with patch("agent.schema_search._load_profile", return_value={}):
        results = search_schema("xyznonexistentqueryterm123")
    assert results == []


def test_tool_wrapper_formats_results_readably():
    with patch("agent.schema_search._load_profile", return_value={}):
        result = search_schema_tool.invoke({"query": "patient registration", "role": "admin"})
    assert "mstpatientregistration" in result


def test_tool_wrapper_respects_role_access():
    with patch("agent.schema_search._load_profile", return_value={}):
        result = search_schema_tool.invoke({"query": "billing collection payment", "role": "lab_tech"})
    # lab_tech has no billing category access — should not see billing tables
    assert "trnmodeofcollectionsdet" not in result


def test_tool_wrapper_handles_no_match_gracefully():
    with patch("agent.schema_search._load_profile", return_value={}):
        result = search_schema_tool.invoke({"query": "xyznonexistentqueryterm123", "role": "admin"})
    assert "No tables matched" in result