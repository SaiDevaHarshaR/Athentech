"""An institution using its OWN AI key must never consume AthenTech's AI; general paths use the shared AI."""
import sys
import types

import pytest

if "pyodbc" not in sys.modules:
    try:
        import pyodbc  # noqa: F401
    except Exception:
        sys.modules["pyodbc"] = types.ModuleType("pyodbc")

import agent.agent as A                       # noqa: E402
from agent import llm_providers as L          # noqa: E402


class RateLimited(Exception):
    pass


def _boom_runnable():
    class R:
        def invoke(self, m): raise RateLimited("Error code: 429 rate limit exceeded")
    return R()


class SharedModel:
    called = 0
    def bind_tools(self, t): return self
    def invoke(self, m):
        SharedModel.called += 1
        return "SHARED ANSWER"


@pytest.fixture(autouse=True)
def _wire(monkeypatch):
    SharedModel.called = 0
    marks = []
    monkeypatch.setattr(A, "_get_provider_chain", lambda: [("groq", SharedModel()), ("openai", SharedModel())])
    monkeypatch.setattr(A, "mark_exhausted", lambda n, ttl_seconds=0: marks.append(n))
    monkeypatch.setattr(A, "is_exhausted", lambda n: False)
    monkeypatch.setattr(A.time, "sleep", lambda s: None)
    monkeypatch.setattr(A, "_is_rate_limit_error", lambda e: "429" in str(e))
    A._marks = marks


def test_shared_request_still_falls_back_when_rate_limited():
    A._OWN_KEY.set(False)
    out = A._invoke_with_retry(_boom_runnable(), ["q"], current_provider="groq")
    assert out == "SHARED ANSWER" and SharedModel.called >= 1


def test_own_key_rate_limit_never_touches_shared_ai(monkeypatch):
    monkeypatch.setattr(L, "institution_chain", lambda c: [("openai", object())])
    A._data_chain("KON1", True)
    assert A._OWN_KEY.get() is True
    with pytest.raises(RateLimited):
        A._invoke_with_retry(_boom_runnable(), ["q"], current_provider="openai")
    assert SharedModel.called == 0 and A._marks == []      # no shared call, shared provider NOT marked exhausted


def test_own_key_rate_limit_becomes_client_message(monkeypatch):
    monkeypatch.setattr(L, "institution_chain", lambda c: [("openai", object())])
    def impl(*a, **k):
        A._data_chain(k["institution_code"], True)
        return A._invoke_with_retry(_boom_runnable(), ["q"], current_provider="openai")
    monkeypatch.setattr(A, "_ask_agent_impl", impl)
    msg, tokens = A.ask_agent(question="q", is_premium=True, institution_code="KON1", db_name="d")
    assert "rate-limiting" in msg and tokens == 0 and SharedModel.called == 0


def test_general_requests_use_shared_chain_even_with_institution_code(monkeypatch):
    def must_not_run(c): raise AssertionError("institution key must not be consulted")
    monkeypatch.setattr(L, "institution_chain", must_not_run)
    A._OWN_KEY.set(True)                                  # stale flag from a previous request
    chain = A._data_chain("KON1", False)                  # not a premium data request (general / AthenTech path)
    assert [n for n, _ in chain] == ["groq", "openai"] and A._OWN_KEY.get() is False


def test_flag_does_not_leak_between_requests(monkeypatch):
    monkeypatch.setattr(L, "institution_chain", lambda c: None if c == "NOKEY" else [("openai", object())])
    A._data_chain("KON1", True); assert A._OWN_KEY.get() is True
    A._data_chain("NOKEY", True); assert A._OWN_KEY.get() is False


def test_flag_reaches_executor_thread_via_copy_context(monkeypatch):
    import asyncio, contextvars
    monkeypatch.setattr(L, "institution_chain", lambda c: [("openai", object())])

    async def go():
        A._data_chain("KON1", True)                      # event-loop thread sets the flag
        ctx = contextvars.copy_context()                 # what generate_patient_report now does
        loop = asyncio.get_running_loop()
        plain = await loop.run_in_executor(None, A._OWN_KEY.get)
        carried = await loop.run_in_executor(None, ctx.run, A._OWN_KEY.get)
        return plain, carried
    plain, carried = asyncio.run(go())
    assert plain is False and carried is True            # proves copy_context is required, and works
