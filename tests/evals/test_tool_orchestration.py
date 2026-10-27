
from unittest.mock import MagicMock


def execute_tool(tool, arguments):
    return tool.invoke(arguments)


def test_agent_calls_sql_tool():

    fake_sql_tool = MagicMock()

    fake_sql_tool.invoke.return_value = (
        "OPRevenue: 125000"
    )

    query_args = {
        "query": "SELECT SUM(Amount) AS OPRevenue FROM Sales"
    }

    result = execute_tool(fake_sql_tool, query_args)

    # TODO 1:
    # Verify that invoke was called exactly once.
    fake_sql_tool.invoke.__________

    # TODO 2:
    # Verify that invoke received the correct arguments.
    fake_sql_tool.invoke.assert_called_once_with(
        __________
    )

    # TODO 3:
    # Verify the tool's returned value.
    assert __________
