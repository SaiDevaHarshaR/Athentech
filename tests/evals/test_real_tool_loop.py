
from unittest.mock import MagicMock
from langchain_core.messages import AIMessage, HumanMessage

import agent.agent as agent_module


def test_sql_tool_loop(monkeypatch):

    fake_tool = MagicMock()
    fake_tool.invoke.return_value = "OPRevenue: 125000"

    # First LLM response requests the SQL tool.
    tool_request = AIMessage(
        content="",
        tool_calls=[{
            "name": "run_sql_query",
            "args": {"query": "SELECT 125000 AS OPRevenue"},
            "id": "call_001",
            "type": "tool_call"
        }]
    )

    # Second LLM response gives the final answer.
    final_response = AIMessage(
        content="OP revenue is 125000"
    )

    # TODO 1:
    # Create an iterator containing the two responses.
    responses = iter([tool_request, final_response])

    # Replace LLM invocation with controlled responses.
    def fake_invoke(*args, **kwargs):
        return next(responses)

    monkeypatch.setattr(
        agent_module,
        "_invoke_with_retry",
        fake_invoke
    )

    answer, tokens = agent_module._run_tool_loop(
        llm_with_tools=MagicMock(),
        messages=[HumanMessage(content="What is OP revenue?")],
        tools_by_name={"run_sql_query": fake_tool}
    )

    # TODO 2:
    # Verify SQL tool received the correct arguments.
    fake_tool.invoke.assert_called_once_with(
        {"query": "SELECT 125000 AS OPRevenue"}
    )

    # TODO 3:
    # Verify the final answer contains the revenue.
    assert answer == "OP revenue is 125000"
