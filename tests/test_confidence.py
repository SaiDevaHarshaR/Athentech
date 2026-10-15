from agent import confidence as C


def _intent(q, a):
    C.begin(q)
    C.note_intent(q, a)
    return C.result()


def _llm(q, ans, ok, args="", bad=(), **kw):
    C.begin(q)
    C.note_tool_call("run_sql_query", {"query": args})
    C.note_llm(ans, list(ok), list(bad), ["run_sql_query"] * max(1, len(ok)), **kw)
    return C.result()


def test_reported_tat_case_is_low():
    r = _intent("which tests have the longest average TAT this week in Kompally branch?",
                "TAT Dashboard This Week COMPLETED 43 WITHIN TAT 9 OUTSIDE TAT 34 Top Delayed Tests IgE")
    assert r["ok"] is False and r["score"] < C.THRESHOLD
    assert any("kompally" in x.lower() for x in r["reasons"])


def test_reported_revenue_case_is_low():
    r = _intent("which branch had the highest revenue last month and how did it compare with the month before?",
                "Collection Growth THIS MONTH 28,949,210 LAST MONTH 63,809,495 Growth 54.6%")
    assert r["ok"] is False


def test_plain_intent_is_ok():
    r = _intent("how many bills today", "Bills Today: 120")
    assert r["ok"] is True


def test_intent_wrong_period_is_flagged():
    r = _intent("refunds yesterday", "Refunds this month: 5")
    assert any("period" in x.lower() for x in r["reasons"])


def test_llm_grounded_numbers_ok():
    r = _llm("top 5 referring doctors by revenue this month", "Dr A earned 1,25,000 and Dr B 98,000.",
             ["DOCTOR | AMT\nDr A | 125000\nDr B | 98000"], "SELECT ... DATEOFBILL >= '2026-10-01'")
    assert r["ok"] is True, r


def test_llm_invented_numbers_low():
    r = _llm("total collection yesterday", "Collection was 9,99,999 and 450 bills.",
             ["TOTAL | BILLS\n210000 | 31"], "SELECT SUM(x)")
    assert r["ok"] is False and r["score"] < C.THRESHOLD


def test_llm_no_data_low():
    r = _llm("total collection yesterday", "Collection was 210000.", [])
    assert r["ok"] is False


def test_llm_missing_branch_name_flagged():
    r = _llm("collection in kompally yesterday", "Collection was 210000.",
             ["TOTAL\n210000"], "SELECT SUM(x) FROM t WHERE d='2026-10-14'")
    assert any("kompally" in x.lower() for x in r["reasons"])
    r2 = _llm("collection in kompally yesterday", "Kompally collection was 210000.",
              ["TOTAL\n210000"], "SELECT ... WHERE branch='KOMPALLY'")
    assert r2["ok"] is True


def test_disabled_and_empty_safe():
    C.begin("x")
    assert C.result() is None
