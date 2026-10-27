
import agent.agent as agent_module


def test_ask_agent_returns_answer(monkeypatch):

    # A fake implementation of the agent.
    def fake_agent(question, **kwargs):
        return "OP revenue is 125000", 25

    # TODO 1:
    # Replace _ask_agent_impl with fake_agent.
    monkeypatch.setattr(
        agent_module,
        "_ask_agent_impl",
        __________
    )

    # TODO 2:
    # Call the real ask_agent with this question:
    # "What is today's OP revenue?"
    answer, tokens = __________

    # TODO 3:
    # Verify the answer is exactly:
    # "OP revenue is 125000"
    assert __________

    # TODO 4:
    # Verify the token count is 25.
    assert __________
