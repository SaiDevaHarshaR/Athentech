
from decimal import Decimal


def normalize_amount(text):
    text = str(text)
    text = text.replace("₹", "")
    text = text.replace(",", "")
    return text.strip()


def compare_amounts(actual, expected):

    # TODO 1:
    # Convert the normalized actual amount into Decimal.
    actual_value = Decimal(actual)

    # TODO 2:
    # Convert the normalized expected amount into Decimal.
    expected_value = Decimal()

    # TODO 3:
    # Return True if both numerical values match.
    return __________


def test_formatted_amount():
    assert compare_amounts("₹1,25,000.00", 125000) is True


def test_incorrect_amount():
    assert compare_amounts("₹1,20,000.00", 125000) is False


def test_refund_amount():
    assert compare_amounts("-₹5,000.00", -5000) is True
