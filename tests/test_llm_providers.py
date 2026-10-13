import types
import pytest
from agent import llm_providers as L


class R:
    def __init__(self, status, text=""):
        self.status_code, self.text = status, text


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
