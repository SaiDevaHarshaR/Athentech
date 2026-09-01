from langchain_core.messages import AIMessage

from agent.agent import _run_tool_loop, MAX_TOOL_ROUNDS


class _FakeTool:
    def __init__(self, name, fn):
        self.name = name
        self._fn = fn

    def invoke(self, args):
        self.calls = getattr(self, "calls", [])
        self.calls.append(args)
        return self._fn(args)


class _FakeLLM:
    def __init__(self, responses):
        self._responses = iter(responses)

    def invoke(self, messages):
        return next(self._responses)


def test_sql_chain_injects_role_and_db_name():
    call_log = []

    def describe(args):
        call_log.append(("describe_table", args))
        return "cols"

    def run_sql(args):
        call_log.append(("run_sql_query", args))
        return "rows"

    tools_by_name = {
        "describe_table": _FakeTool("describe_table", describe),
        "run_sql_query": _FakeTool("run_sql_query", run_sql),
    }
    responses = [
        AIMessage(content="", tool_calls=[{"name": "describe_table", "args": {"table_name": "x"}, "id": "c1"}]),
        AIMessage(content="", tool_calls=[{"name": "run_sql_query", "args": {"query": "SELECT 1"}, "id": "c2"}]),
        AIMessage(content="Final SQL answer", tool_calls=[]),
    ]

    result = _run_tool_loop(
        _FakeLLM(responses), [], tools_by_name,
        tool_extra_kwargs={
            "run_sql_query": {"role": "doctor", "db_name": "testdb"},
            "describe_table": {"role": "doctor", "db_name": "testdb"},
        }
    )

    assert result == "Final SQL answer"
    assert call_log[0][1]["role"] == "doctor"
    assert call_log[0][1]["db_name"] == "testdb"


def test_web_search_can_chain_a_second_call():
    """
    This is the exact bug that made normal mode return "No relevant
    information found" even when the first search succeeded: the old
    code only handled a single tool-call round, so if the model called
    web_search a second time, the response had no .content (it's a
    tool-call response) and the code silently gave up.
    """
    call_log = []

    def search(args):
        call_log.append(args)
        return f"results for {args['query']}"

    tools_by_name = {"web_search": _FakeTool("web_search", search)}
    responses = [
        AIMessage(content="", tool_calls=[{"name": "web_search", "args": {"query": "hospitals in Malkajgiri"}, "id": "c1"}]),
        AIMessage(content="", tool_calls=[{"name": "web_search", "args": {"query": "best hospitals Malkajgiri Hyderabad"}, "id": "c2"}]),
        AIMessage(content="Here are good hospitals in Malkajgiri: ...", tool_calls=[]),
    ]

    result = _run_tool_loop(_FakeLLM(responses), [], tools_by_name)

    assert result == "Here are good hospitals in Malkajgiri: ..."
    assert len(call_log) == 2
    # web_search's signature doesn't take role/db_name — must never get them injected.
    assert "role" not in call_log[0]
    assert "db_name" not in call_log[0]


def test_loop_stops_at_max_rounds_without_hanging_forever():
    def always_call_tool(args):
        return "keep going"

    tools_by_name = {"describe_table": _FakeTool("describe_table", always_call_tool)}

    class InfiniteToolCaller:
        def invoke(self, messages):
            return AIMessage(content="", tool_calls=[{"name": "describe_table", "args": {"table_name": "x"}, "id": "loop"}])

    call_count = {"n": 0}
    orig_invoke = tools_by_name["describe_table"].invoke

    def counting_invoke(args):
        call_count["n"] += 1
        return orig_invoke(args)
    tools_by_name["describe_table"].invoke = counting_invoke

    try:
        _run_tool_loop(InfiniteToolCaller(), [], tools_by_name)
    except Exception:
        pass  # the final fallback calls the real llm, which will fail without network — that's fine, we only care about the round cap

    assert call_count["n"] == MAX_TOOL_ROUNDS