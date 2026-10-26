
import pytest

# Expected results from a trusted synthetic database
EXPECTED = {
    "op": 125000,
    "ip": 340000
}


def evaluate_revenue(actual, expected):
    results = {}

    # Task A: Is actual OP equal to expected OP?
    results["op_correct"] = (
        actual.get("op") == expected.get("op")
    )

    # Task B: Is actual IP equal to expected IP?
    results["ip_correct"] = (
        actual.get("ip") == expected.get("ip")
    )

    # Task C: Are both values present?
    results["complete"] = (
        actual.get("op") is not None
        and
        actual.get("ip") is not None
    )

    return results


def test_complete_answer():
    actual = {
        "op": 125000,
        "ip": 340000
    }

    scores = evaluate_revenue(actual, EXPECTED)

    assert all(scores.values())


def test_incomplete_answer():
    actual = {
        "op": 125000,
        "ip": None
    }

    scores = evaluate_revenue(actual, EXPECTED)

    assert scores["complete"] is False
    assert scores["ip_correct"] is False
