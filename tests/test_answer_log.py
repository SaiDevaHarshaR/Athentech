import importlib
import os
import tempfile

import pytest

from agent import confidence as C


@pytest.fixture()
def AL(monkeypatch):
    d = tempfile.mkdtemp()
    monkeypatch.setenv("SAHASRA_ANSWER_DB", os.path.join(d, "t.db"))
    import agent.answer_log as m
    importlib.reload(m)
    return m


def _llm_with_sql():
    C.begin("collection in kompally yesterday")
    C.note_tool_call("run_sql_query", {"query": "SELECT SUM(x) FROM trnmodeofcollectionsdet t JOIN mstbranch b ON b.id=t.b", "role": "admin"})
    C.note_llm("Kompally collection was 210000.", ["TOTAL\n210000"], [], ["run_sql_query"])
    return C.result(), C.explain(True)


def test_explain_has_sql_for_admin_only():
    _llm_with_sql()
    full, pub = C.explain(True), C.explain(False)
    assert full["queries"] and "trnmodeofcollectionsdet" in full["tables"] and "mstbranch" in full["tables"]
    assert "queries" not in pub and pub["tables"]


def test_explain_never_contains_credentials():
    C.begin("x")
    C.note_tool_call("run_sql_query", {"query": "SELECT 1"})   # extra kwargs (db_password) are added after this call
    C.note_llm("ok 100", ["1"], [], ["run_sql_query"])
    assert "password" not in str(C.explain(True)).lower()


def test_log_and_vote_ownership(AL):
    conf, ex = _llm_with_sql()
    aid = AL.log_answer("KONNECT", "admin", "q 9876543210", "ans", conf, ex)
    assert aid
    assert AL.set_vote(aid, "OTHERCLIENT", "down", "x") is False      # other institution can't vote
    assert AL.set_vote(aid, "KONNECT", "down", "wrong branch") is True
    assert AL.set_vote(aid, "KONNECT", "sideways") is False
    rows = AL.list_rows("open")
    assert len(rows) == 1 and rows[0]["vote"] == "down"
    assert "9876543210" not in rows[0]["question"]                    # phone masked


def test_low_score_kept_with_preview_and_resolve(AL):
    C.begin("refunds today in uppal branch")
    C.note_intent("refunds today in uppal branch", "Total Refunds Today 7650")
    conf, ex = C.result(), C.explain(True)
    aid = AL.log_answer("KONNECT", "admin", "refunds today in uppal branch", "Total Refunds Today 7650", conf, ex)
    rows = AL.list_rows("low")
    assert rows and rows[0]["preview"] and rows[0]["ok"] == 0
    assert AL.resolve(aid, "added branch filter")
    assert AL.list_rows("open") == []
    assert AL.stats()["answers"] == 1


def test_never_raises_on_bad_input(AL):
    assert AL.log_answer(None, None, None, None, None, None)
    assert AL.set_vote("abc", "x", "up") is False
