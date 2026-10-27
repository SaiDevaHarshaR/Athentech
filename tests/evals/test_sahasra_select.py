
import pytest
from unittest.mock import MagicMock

import agent.tools as tools


@pytest.fixture
def fake_database(monkeypatch):
    connection = MagicMock()
    cursor = connection.cursor.return_value

    # Fake MSSQL column metadata
    cursor.description = [
        ("OPRevenue",),
        ("IPRevenue",)
    ]

    # Fake MSSQL result row
    cursor.fetchmany.return_value = [
        (125000, 340000)
    ]

    # Replace access and schema checks for this
    # connection-flow test only.
    monkeypatch.setattr(
        tools,
        "check_query_access",
        lambda role, query: (True, "")
    )

    monkeypatch.setattr(
        tools,
        "_validate_sql_columns",
        lambda cursor, query: (True, "")
    )

    # TODO 1:
    # Replace tools.get_hospital_connection
    # so that it returns our fake connection.
    monkeypatch.setattr(
        tools,
        "get_hospital_connection",
        lambda *args, **kwargs: connection
    )

    return connection


def test_select_revenue(fake_database):
    sql = "SELECT OPRevenue, IPRevenue FROM DailyRevenue"

    result = tools.run_sql_query.invoke({
        "query": sql,
        "role": "viewer"
    })

    # TODO 2: Verify OP revenue appears
    assert "OPRevenue" in result

    # TODO 3: Verify IP revenue appears
    assert "IPRevenue" in result

    # TODO 4: Verify SQL was executed once
    cursor = fake_database.cursor.return_value
    cursor.execute.assert_called_once()

    # TODO 5: Verify connection was closed
    fake_database.close.assert_called_once()
