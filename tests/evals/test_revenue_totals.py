
from decimal import Decimal


def evaluate_revenue_totals(actual, expected):
    scores = {}

    # TODO 1:
    # Check actual OP equals expected OP.
    scores["op_correct"] = actual.get(op) == expected.get(op)

    # TODO 2:
    # Check actual IP equals expected IP.
    scores["ip_correct"] = __________

    # TODO 3:
    # Calculate the trusted total from expected.
    expected_total = __________

    # TODO 4:
    # Compare actual total to expected total.
    scores["total_correct"] = __________

    return scores


def test_all_correct():
    actual = {
        "op": Decimal("125000"),
        "ip": Decimal("340000"),
        "total": Decimal("465000")
    }
    expected = {
        "op": Decimal("125000"),
        "ip": Decimal("340000")
    }

    scores = evaluate_revenue_totals(actual, expected)

    assert all(scores.values())


def test_wrong_total():
    actual = {
        "op": Decimal("125000"),
        "ip": Decimal("340000"),
        "total": Decimal("450000")
    }
    expected = {
        "op": Decimal("125000"),
        "ip": Decimal("340000")
    }

    scores = evaluate_revenue_totals(actual, expected)

    assert scores["op_correct"] is True
    assert scores["ip_correct"] is True
    assert scores["total_correct"] is False
