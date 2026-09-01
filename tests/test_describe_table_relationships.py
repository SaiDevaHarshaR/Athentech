from unittest.mock import patch, MagicMock

import auth.table_relationships as rel_mod
from agent.tools import describe_table


class FakeCursor:
    def __init__(self, rows):
        self._rows = rows

    def execute(self, *a, **k):
        pass

    def fetchall(self):
        return self._rows


class FakeConn:
    def cursor(self):
        return FakeCursor([("ID", "int"), ("PatientID", "int"), ("Amount", "money")])

    def close(self):
        pass


def test_describe_table_includes_known_relationships(monkeypatch):
    monkeypatch.setitem(
        rel_mod.REAL_TABLE_RELATIONSHIPS,
        "trninvoicepayments",
        [("PatientID", "mstpatientregistration", "ID")],
    )

    with patch("agent.tools.get_hospital_connection", return_value=FakeConn()), \
         patch("agent.tools.check_table_access", return_value=(True, "trninvoicepayments")):
        result = describe_table.invoke({"table_name": "trninvoicepayments", "role": "admin"})

    assert "Known joins:" in result
    assert "trninvoicepayments.PatientID = mstpatientregistration.ID" in result


def test_describe_table_omits_relationships_section_when_none_known(monkeypatch):
    monkeypatch.setitem(rel_mod.REAL_TABLE_RELATIONSHIPS, "sometableneverset", [])
    # ensure it's genuinely absent, not just empty
    rel_mod.REAL_TABLE_RELATIONSHIPS.pop("sometableneverset", None)

    with patch("agent.tools.get_hospital_connection", return_value=FakeConn()), \
         patch("agent.tools.check_table_access", return_value=(True, "sometableneverset")):
        result = describe_table.invoke({"table_name": "sometableneverset", "role": "admin"})

    assert "Known joins:" not in result