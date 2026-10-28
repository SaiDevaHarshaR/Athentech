
import re
from decimal import Decimal


def extract_revenue(answer):
    pattern = (
        r"OP revenue is ₹?(?P<op>[\d,]+)"
        r"\s+and\s+"
        r"IP revenue is ₹?(?P<ip>[\d,]+)"
    )

    match = re.search(pattern, answer, re.IGNORECASE)

    if not match:
        return None

    # TODO 1:
    # Extract OP text from named group "op".
    op_text = __________

    # TODO 2:
    # Extract IP text from named group "ip".
    ip_text = __________

    # TODO 3:
    # Remove commas and convert OP to Decimal.
    op_amount = __________

    # TODO 4:
    # Remove commas and convert IP to Decimal.
    ip_amount = __________

    return {
        "op": op_amount,
        "ip": ip_amount
    }


def test_extract_revenue():
    answer = (
        "OP revenue is ₹1,25,000 "
        "and IP revenue is ₹3,40,000"
    )

    result = extract_revenue(answer)

    assert result["op"] == Decimal("125000")
    assert result["ip"] == Decimal("340000")


def test_missing_ip():
    answer = "OP revenue is ₹1,25,000"

    assert extract_revenue(answer) is None
