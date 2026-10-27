
import pytest


@pytest.fixture
def expected_revenue():
    return {
        "op": 125000,
        "ip": 340000
    }


def evaluate_answer(actual, expected):
    return {
        "op_correct": actual.get("op") == expected["op"],
        "ip_correct": actual.get("ip") == expected["ip"],
        "complete": (
            actual.get("op") is not None
            and actual.get("ip") is not None
        )
    }


@pytest.mark.parametrize(
    "actual, should_pass",
    [
        ({"op": 125000, "ip": 340000}, True),
        ({"op": 125000, "ip": None}, False),
        ({"op": 100000, "ip": 340000}, False),
        ({"op": 125000, "ip": 300000}, False),
    ]
)
def test_revenue_regression(actual, should_pass, expected_revenue):

    scores = evaluate_answer(actual, expected_revenue)

    # TODO 1:
    # Determine whether every evaluation criterion passed.
    all_passed = all({"actual": True, "should_pass": True, "expected_revenue": True}) 

    # TODO 2:
    # Compare the evaluation outcome
    # with should_pass.
    assert all_passed.values() == should_pass
