
import pytest
from unittest.mock import MagicMock


def get_revenue(connection):
    cursor = connection.cursor()

    cursor.execute(
        "SELECT OPRevenue, IPRevenue FROM DailyRevenue"
    )

    return cursor.fetchone()


@pytest.fixture
def mock_connection():
    connection = MagicMock()

    # TODO 1:
    # Make fetchone() return the tuple
    # (125000, 340000).
    connection.cursor.return_value.fetchone.return_value = ...

    return connection


def test_revenue_from_mock(mock_connection):
    revenue = get_revenue(mock_connection)

    # TODO 2:
    # Verify the OP value (index 0).
    assert ...

    # TODO 3:
    # Verify the IP value (index 1).
    assert ...

    # TODO 4:
    # Verify that execute() was called once.
    mock_connection.cursor.return_value.execute._____
