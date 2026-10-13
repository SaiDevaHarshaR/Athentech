import types
import pytest
from agent import llm_providers as L


class R:
    def __init__(self, status, text=""):
        self.status_code, self.text = status, text

    def json(self):
        return {"choices": [{"message": {"content": "hi"}}]}


def _patch(monkeypatch, get, post):
    monkeypatch.setattr(L.requests, "get", lambda *a, **k: get)
    monkeypatch.setattr(L.requests, "post", lambda *a, **k: post)


def test_catalog_has_25_unique():
    ids = [p["id"] for p in L.CATALOG]
    assert len(ids) == 25 == len(set(ids))


@pytest.mark.parametrize("get,post,code", [
    (R(200), R(200, "{}"), "ok"),
    (R(401, "Incorrect API key provided"), R(401), "invalid_key"),
    (R(200), R(429, '{"error":{"code":"insufficient_quota","message":"You exceeded your current quota"}}'), "no_credits"),
    (R(200), R(402, "Insufficient Balance"), "no_credits"),
    (R(200), R(400, '{"error":{"message":"Your credit balance is too low to access the Anthropic API"}}'), "no_credits"),
    (R(200), R(429, "Rate limit reached for requests per minute"), "rate_limited"),
    (R(200), R(404, "The model `x` does not exist"), "bad_model"),
    (R(200), R(503, "down"), "unreachable"),
    (R(404), R(403, "API key not valid. Please pass a valid API key."), "invalid_key"),
])
def test_validate_codes(monkeypatch, get, post, code):
    _patch(monkeypatch, get, post)
    r = L.validate_key("openai", "sk-test")
    assert r["code"] == code and r["ok"] == (code == "ok") and "sk-test" not in r["message"]


def test_validate_network_error(monkeypatch):
    def boom(*a, **k): raise L.requests.exceptions.ConnectionError("x")
    monkeypatch.setattr(L.requests, "get", boom)
    assert L.validate_key("groq", "k")["code"] == "unreachable"


def test_validate_input_checks():
    assert L.validate_key("nope", "k")["code"] == "bad_request"
    assert L.validate_key("openai", "")["code"] == "invalid_key"
    assert L.validate_key("custom", "k", model="m", base_url="http://insecure")["code"] == "bad_request"


def test_runtime_classification():
    class E(Exception): status_code = 401
    assert L.classify_runtime_error(E("x")) == "invalid_key"
    assert L.classify_runtime_error(Exception("Error code: 429 insufficient_quota")) == "no_credits"
    assert L.classify_runtime_error(Exception("429 rate limit")) == "rate_limited"
    assert L.classify_runtime_error(Exception("boom")) is None


def test_fail_closed_when_key_configured_but_unusable(monkeypatch):
    L.invalidate()
    monkeypatch.setattr(L, "institution_llm_settings", lambda c: (_ for _ in ()).throw(RuntimeError("db down")))
    with pytest.raises(L.ByokUnavailable):
        L.institution_chain("X1")
    L.invalidate()
    monkeypatch.setattr(L, "institution_llm_settings", lambda c: {"provider": "openai", "api_key": "k", "model": None, "base_url": None})
    monkeypatch.setattr(L, "build_chat_model", lambda *a, **k: (_ for _ in ()).throw(ImportError("x")))
    with pytest.raises(L.ByokUnavailable):
        L.institution_chain("X2")


def test_unmigrated_columns_mean_shared_ai(monkeypatch):
    import types, sys
    mod = types.ModuleType("database.byok_migration"); mod.READY = False
    pkg = types.ModuleType("database"); pkg.byok_migration = mod
    monkeypatch.setitem(sys.modules, "database", pkg); monkeypatch.setitem(sys.modules, "database.byok_migration", mod)
    L.invalidate()
    monkeypatch.setattr(L, "institution_llm_settings", lambda c: (_ for _ in ()).throw(RuntimeError("Invalid column name 'llm_provider'")))
    assert L.institution_chain("X3") is None


def test_200_without_real_completion_is_rejected(monkeypatch):
    class J(R):
        def __init__(s, st, j): super().__init__(st); s._j = j
        def json(s): return s._j
    monkeypatch.setattr(L.requests, "get", lambda *a, **k: R(200))
    monkeypatch.setattr(L.requests, "post", lambda *a, **k: J(200, {"hello": "world"}))
    assert L.validate_key("openai", "k")["code"] == "bad_request"
    monkeypatch.setattr(L.requests, "post", lambda *a, **k: J(200, {"choices": [{"message": {"content": "hi"}}]}))
    assert L.validate_key("openai", "k")["ok"]


def test_ssrf_guard(monkeypatch):
    for bad in ("http://example.com", "https://127.0.0.1", "https://169.254.169.254/latest", "https://10.0.0.5/v1",
                "https://user:pw@example.com", "https://localhost/v1"):
        assert not L.check_base_url(bad)[0], bad
    monkeypatch.setenv("BYOK_ALLOW_CUSTOM", "1")
    assert L.validate_key("custom", "k", model="m", base_url="https://169.254.169.254")["code"] == "bad_request"
    monkeypatch.delenv("BYOK_ALLOW_CUSTOM")
    assert "disabled" in L.validate_key("custom", "k", model="m", base_url="https://api.example.com")["message"]


def test_only_custom_may_override_url(monkeypatch):
    seen = {}
    monkeypatch.setattr(L.requests, "get", lambda url, **k: seen.setdefault("url", url) and R(401, "invalid api key"))
    L.validate_key("openai", "k", base_url="https://evil.example.com")
    assert seen["url"].startswith("https://api.openai.com/")


def test_schema_regression_after_successful_migration_fails_closed(monkeypatch):
    import types, sys
    mod = types.ModuleType("database.byok_migration"); mod.READY = True
    pkg = types.ModuleType("database")
    monkeypatch.setitem(sys.modules, "database", pkg); monkeypatch.setitem(sys.modules, "database.byok_migration", mod)
    pkg.byok_migration = mod
    L.invalidate()
    monkeypatch.setattr(L, "institution_llm_settings", lambda c: (_ for _ in ()).throw(RuntimeError("Invalid column name 'llm_provider'")))
    with pytest.raises(L.ByokUnavailable):
        L.institution_chain("X9")
