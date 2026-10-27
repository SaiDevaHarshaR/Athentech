
import re


def evaluate_revenue_answer(answer, expected_amount):

    # Extract numbers from the agent's answer.
    numbers = re.findall(r"\d+", answer)

    # TODO 1:
    # Convert the expected amount to a string.
    expected_text = str(expected_amount)

    # TODO 2:
    # Return True if expected_text is in numbers.
    return expected_text in numbers



def test_correct_answer():
    answer = "OP revenue is 125000"

    assert evaluate_revenue_answer(answer, 125000) is True


def test_wrong_answer():
    answer = "OP revenue is 150000"

    assert evaluate_revenue_answer(answer, 125000) is False

