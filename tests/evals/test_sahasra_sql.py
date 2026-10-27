
import pytest

from agent.tools import run_sql_query


def test_reject_update_query():

    unsafe_sql = ("UPDATE trnSalesMst " "SET Paid = 0")
    # TODO 1:
    # Call Sahasra's real run_sql_query
    # using unsafe_sql as the query.
    # Hint: run_sql_query is a LangChain tool;
    # use .invoke() with an argument dictionary.
    result = run_sql_query.invoke({"query": unsafe_sql })
    # TODO 2:
    # Verify that the returned message
    # indicates that only SELECT is allowed.

    assert result == "Error: Only SELECT queries are allowed."
