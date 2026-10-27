import agent.agent as agent_module
def test_agent_receives_correct_context(monkeypatch):
    captured = {}
    def fake_agent(question, **kwargs):
        captured["question"] = question
        captured["role"] = kwargs.get("role")
        captured["db_name"] = kwargs.get("db_name")
        captured["institution_code"] = kwargs.get("institution_code")
        return "Revenue report ready", 15
    monkeypatch.setattr(
        agent_module,
        "_ask_agent_impl",
        fake_agent
    )
    answer, tokens = agent_module.ask_agent(
        question="Show today's revenue",
        role="viewer",
        db_name="hospital_demo",
        institution_code="HOSP001"
    )
    # TODO 1: Verify captured role is viewer.
    assert captured["role"] == "viewer"
    # TODO 2: Verify database name.
    assert captured["db_name"] == "hospital_demo"
    # TODO 3: Verify institution code.
    assert captured["institution_code"] == "HOSP001"
    # TODO 4: Verify question was passed correctly.
    assert captured["question"] == "Show today's revenue"
    # TODO 5: Verify the answer.
    assert fake_agent == 15
