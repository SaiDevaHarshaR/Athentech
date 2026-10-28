
import re
from decimal import Decimal
import agent.agent as agent_module


def extract_revenue(answer):
    pattern = (
        r"OP revenue is ₹?(?P<op>[\d,]+)"
        r"\s+and\s+"
        r"IP revenue is ₹?(?P<ip>[\d,]+)"
    )

    match = re.search(pattern, answer, re.IGNORECASE)

    if not match:
        return None

    return {
        "op": Decimal(match.group("op").replace(",", "")),
        "ip": Decimal(match.group("ip").replace(",", ""))
    }


def test_agent_revenue_answer(monkeypatch):

    # Trusted synthetic SQL results
    expected = {
        "op": Decimal("125000"),
        "ip": Decimal("340000")
    }

    def fake_agent(question, **kwargs):
        return (
            "OP revenue is ₹1,25,000 and "
            "IP revenue is ₹3,40,000",
            25
        )

    monkeypatch.setattr(
        agent_module,
        "_ask_agent_impl",
        fake_agent
    )

    # TODO 1:
    # Call the real ask_agent function.
    answer, tokens = agent_module.ask_agent("query"="Compare today's OP and IP revenue")

    # TODO 2:
    # Extract OP/IP revenue from the answer.
    actual = extract_revenue(answer)

    # TODO 3:
    # Verify extraction succeeded.
    assert actual is not None

    # TODO 4:
    # Verify OP matches the trusted amount.
    assert expected["op"] == actual["op"]

    # TODO 5:
    # Verify IP matches the trusted amount.
    assert expected["ip"] == actual["ip"]
