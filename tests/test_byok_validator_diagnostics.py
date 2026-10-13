"""Offline unit tests; no live vendor keys or SQL Server needed."""
import pytest
from agent import llm_providers as L


class Resp:
    def __init__(self, status=200, data=None, text="", content_type="application/json"):
        self.status_code = status
        self._data = data
        self.text = text
        self.headers = {"content-type": content_type}

    def json(self):
        if self._data is None:
            raise ValueError("not JSON")
        return self._data


def ok_openai():
    return Resp(200, {"choices": [{"message": {"role": "assistant", "content": "OK"}}]})


def test_real_inference_only_and_64_tokens(monkeypatch):
    seen = []
    monkeypatch.setattr(L.requests, "get", lambda *a, **k: pytest.fail("Do not require /models"))
    def call(url, **kwargs):
        seen.append((url, kwargs))
        return ok_openai()
    monkeypatch.setattr(L.requests, "post", call)
    for provider in ("openai", "gemini", "groq", "mistral"):
        result = L.validate_key(provider, "VALID_TEST_KEY")
        assert result["ok"] and result["code"] == "ok"
    assert len(seen) == 4
    for url, kwargs in seen:
        assert url.endswith("/chat/completions")
        assert kwargs["json"]["max_tokens"] == 64
        assert not kwargs["allow_redirects"]
        assert kwargs["headers"]["Authorization"] == "Bearer VALID_TEST_KEY"


def test_anthropic_protocol_success(monkeypatch):
    def call(url, **kwargs):
        assert url.endswith("/messages")
        assert kwargs["headers"]["x-api-key"] == "TEST_KEY"
        return Resp(200, {"content": [{"type": "text", "text": "OK"}]})
    monkeypatch.setattr(L.requests, "post", call)
    assert L.validate_key("anthropic", "TEST_KEY")["ok"]


@pytest.mark.parametrize("status,body,expected", [
    (401, {"error": {"code": "invalid_api_key", "message": "invalid API key"}}, "invalid_key"),
    (403, {"error": {"type": "permission_denied", "message": "project restricted"}}, "access_denied"),
    (429, {"error": {"code": "insufficient_quota", "message": "quota exhausted"}}, "no_credits"),
    (429, {"error": {"message": "Rate limit RPM exceeded"}}, "rate_limited"),
    (404, {"error": {"message": "model x does not exist"}}, "bad_model"),
    (404, {"error": {"message": "route does not exist"}}, "endpoint_missing"),
    (503, {"error": {"message": "service unavailable"}}, "provider_error"),
    (200, {"unexpected": "not a completion"}, "invalid_response"),
])
def test_distinct_provider_errors(monkeypatch, status, body, expected):
    monkeypatch.setattr(L.requests, "post", lambda *a, **kw: Resp(status, body))
    got = L.validate_key("openai", "TEST_KEY")
    assert got["code"] == expected and got["ok"] is False
    assert got["http_status"] == status


def test_recover_from_deprecated_max_tokens(monkeypatch):
    count = []
    def call(url, **kwargs):
        count.append(kwargs["json"].copy())
        if len(count) == 1:
            return Resp(400, {"error": {"message": "Unsupported parameter: max_tokens; use max_completion_tokens"}})
        return ok_openai()
    monkeypatch.setattr(L.requests, "post", call)
    assert L.validate_key("openai", "TEST_KEY")["ok"]
    assert "max_tokens" in count[0]
    assert "max_completion_tokens" in count[1]
    assert len(count) == 2


def test_network_error_reveals_type_without_key(monkeypatch):
    def fail(*a, **kwargs):
        raise L.requests.exceptions.SSLError("bad certificate sk-VISIBLE1234567890")
    monkeypatch.setattr(L.requests, "post", fail)
    got = L.validate_key("openai", "sk-VISIBLE1234567890")
    assert got["code"] == "tls_error"
    assert "sk-" not in str(got)


def test_key_omitted_from_provider_details(monkeypatch):
    key = "sk-SUPERSECRETVALIDKEY123"
    monkeypatch.setattr(L.requests, "post", lambda *a, **kw: Resp(400, {"error": {"message": "Bad request token=" + key}}))
    got = L.validate_key("openai", key)
    assert key not in str(got)
    assert "REDACTED" in got["detail"]


def test_retired_github_disabled():
    catalog_entry = next(p for p in L.CATALOG if p["id"] == "github")
    assert catalog_entry["disabled"] is True
    assert "retired" in L.validate_key("github", "any")["message"].lower()
