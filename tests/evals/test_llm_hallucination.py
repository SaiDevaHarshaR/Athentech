
from decimal import Decimal
from unittest.mock import MagicMock

from langchain_core.messages import AIMessage, HumanMessage

import agent.agent as agent_module


def test_detect_wrong_revenue(monkeypatch):

    # Trusted synthetic SQL result
    expected_op = Decimal("125000")

    # Simulated SQL tool
    fake_sql = MagicMock()
    fake_sql.invoke.return_value = "OPRevenue: 125000"

    # First LLM response: calls SQL tool
    tool_request = AIMessage(
        content="",
        tool_calls=[{
            "name": "run_sql_query",
            "args": {"query": "SELECT 125000 AS OPRevenue"},
            "id": "call_001",
            "type": "tool_call"
        }]
    )

    # Second LLM response: WRONG revenue
    wrong_response = AIMessage(
        content="OP revenue is 150000"
    )

    responses = iter([tool_request, wrong_response])

    monkeypatch.setattr(
        agent_module,
        "_invoke_with_retry",
        lambda *args, **kwargs: next(responses)
    )

    answer, tokens = agent_module._run_tool_loop(
        llm_with_tools=MagicMock(),
        messages=[HumanMessage(content="What is OP revenue?")],
        tools_by_name={"run_sql_query": fake_sql}
    )

    # TODO 1:
    # Extract the amount from the answer.
    # Assume format: "OP revenue is 150000".
    actual_op = answer.group("150000")

    # TODO 2:
    # Check whether actual OP matches expected OP.
    is_correct = Decimal(actual_op) == expected_op

    # TODO 3:
    # The evaluator should recognize a wrong answer.
    assert is_correct is False
