"""Bring-your-own-key (BYOK): provider catalog, key validation, per-institution chat model.

Most providers speak the OpenAI chat-completions protocol, so one code path covers them.
NOTE: base URLs / default models are the providers' documented values at time of writing but were
NOT exercised against the live providers from the build sandbox. Validation reports the real answer at
runtime, and an admin can override the model (or use the 'custom' provider with any OpenAI-compatible URL).
"""
import ipaddress
import os
import re
import socket
import threading
from urllib.parse import urlparse
import time

import requests

# id: (label, protocol, base_url, default_model, key_page)
_P = {
    "openai":      ("OpenAI", "openai", "https://api.openai.com/v1", "gpt-4o-mini", "platform.openai.com/api-keys"),
    "gemini":      ("Google Gemini", "openai", "https://generativelanguage.googleapis.com/v1beta/openai", "gemini-2.5-flash", "aistudio.google.com/apikey"),
    "anthropic":   ("Anthropic Claude", "anthropic", "https://api.anthropic.com/v1", "claude-haiku-4-5", "console.anthropic.com"),
    "groq":        ("Groq", "openai", "https://api.groq.com/openai/v1", "openai/gpt-oss-20b", "console.groq.com/keys"),
    "mistral":     ("Mistral AI", "openai", "https://api.mistral.ai/v1", "mistral-small-latest", "console.mistral.ai"),
    "cohere":      ("Cohere", "openai", "https://api.cohere.ai/compatibility/v1", "command-a-03-2025", "dashboard.cohere.com/api-keys"),
    "openrouter":  ("OpenRouter", "openai", "https://openrouter.ai/api/v1", "openai/gpt-4o-mini", "openrouter.ai/keys"),
    "together":    ("Together AI", "openai", "https://api.together.xyz/v1", "meta-llama/Llama-3.3-70B-Instruct-Turbo", "api.together.ai"),
    "fireworks":   ("Fireworks AI", "openai", "https://api.fireworks.ai/inference/v1", "accounts/fireworks/models/llama-v3p3-70b-instruct", "fireworks.ai"),
    "deepseek":    ("DeepSeek", "openai", "https://api.deepseek.com/v1", "deepseek-chat", "platform.deepseek.com"),
    "xai":         ("xAI Grok", "openai", "https://api.x.ai/v1", "grok-3-mini", "console.x.ai"),
    "cerebras":    ("Cerebras", "openai", "https://api.cerebras.ai/v1", "llama-3.3-70b", "cloud.cerebras.ai"),
    "sambanova":   ("SambaNova", "openai", "https://api.sambanova.ai/v1", "Meta-Llama-3.3-70B-Instruct", "cloud.sambanova.ai"),
    "deepinfra":   ("DeepInfra", "openai", "https://api.deepinfra.com/v1/openai", "meta-llama/Llama-3.3-70B-Instruct", "deepinfra.com/dash/api_keys"),
    "nvidia":      ("NVIDIA NIM", "openai", "https://integrate.api.nvidia.com/v1", "meta/llama-3.3-70b-instruct", "build.nvidia.com"),
    "hyperbolic":  ("Hyperbolic", "openai", "https://api.hyperbolic.xyz/v1", "meta-llama/Llama-3.3-70B-Instruct", "app.hyperbolic.xyz"),
    "novita":      ("Novita AI", "openai", "https://api.novita.ai/v3/openai", "meta-llama/llama-3.3-70b-instruct", "novita.ai"),
    "moonshot":    ("Moonshot Kimi", "openai", "https://api.moonshot.ai/v1", "kimi-k2-0905-preview", "platform.moonshot.ai"),
    "zhipu":       ("Zhipu GLM", "openai", "https://open.bigmodel.cn/api/paas/v4", "glm-4-flash", "open.bigmodel.cn"),
    "qwen":        ("Alibaba Qwen (DashScope)", "openai", "https://dashscope-intl.aliyuncs.com/compatible-mode/v1", "qwen-plus", "bailian.console.alibabacloud.com"),
    "siliconflow": ("SiliconFlow", "openai", "https://api.siliconflow.cn/v1", "Qwen/Qwen2.5-72B-Instruct", "cloud.siliconflow.cn"),
    "github":      ("GitHub Models (retired)", "openai", "https://models.inference.ai.azure.com", "gpt-4o-mini", "github.com/settings/tokens"),
    "huggingface": ("Hugging Face", "openai", "https://router.huggingface.co/v1", "meta-llama/Llama-3.3-70B-Instruct", "huggingface.co/settings/tokens"),
    "ai21":        ("AI21 Jamba", "openai", "https://api.ai21.com/studio/v1", "jamba-large", "studio.ai21.com"),
    "custom":      ("Other (OpenAI-compatible URL)", "openai", "", "", ""),
}

CATALOG = [{"id": k, "label": v[0], "base_url": v[2], "default_model": v[3], "key_page": v[4],
            "needs_base_url": k == "custom", "disabled": k == "github",
            "reason": "GitHub Models inference API was retired July 30, 2026." if k == "github" else ""}
           for k, v in _P.items()]

# Validation must test INFERENCE. Some vendors do not support GET /models, and
# a 1-token chat may be rejected by the selected model even with a good key.
_CREDIT = re.compile(
    r"insufficient[_ -]?(quota|balance|funds|credits?)|billing[_ -]?(hard[_ -]?)?limit|"
    r"exceeded your current quota|credit balance|out of credits?|no credits?|"
    r"payment required|balance is too low|quota (exceeded|exhausted)|"
    r"resource_exhausted|not enough (credit|balance)|top.?up|add (a )?payment|"
    r"exhausted (balance|credits?|quota)|insufficient funds", re.I)
_BADKEY = re.compile(
    r"invalid[_ -]?(api[_ -]?)?key|incorrect api key|invalid x-api-key|"
    r"api key not valid|api_key_invalid|authentication[_ -]?(error|failed)|"
    r"invalid (authentication|token|credential)|bad credentials|unauthenticated|"
    r"invalid authorization|incorrect (token|key)", re.I)
_BADMODEL = re.compile(
    r"model.{0,80}(not found|does not exist|not supported|unknown|decommission|"
    r"invalid|not available)|no such model|model_not_found|invalid_model", re.I)
_ACCESS = re.compile(r"permission[_ -]?denied|not authorized to (use|access)|"
                     r"access denied|model.{0,50}(permission|not allowed|not enabled)", re.I)

MESSAGES = {
    "ok": "API key validated successfully. Live model inference works.",
    "invalid_key": "Authentication failed. Confirm the key belongs to the selected provider.",
    "no_credits": "The provider reports insufficient credits or quota. Check the account billing and quotas.",
    "rate_limited": "The provider is rate-limiting requests. Wait for its retry window, then test again.",
    "bad_model": "The selected model is unavailable or not recognized. Try an available model ID for this account.",
    "access_denied": "The provider denied this model or account access. Check project permissions, region and model access.",
    "unreachable": "The Sahasra SERVER could not connect to the provider. Check outbound HTTPS, DNS, proxy and TLS.",
    "timeout": "The provider verification request timed out. Check server connectivity and try again.",
    "tls_error": "Secure HTTPS verification failed. Check the server's CA certificates, TLS and inspection proxy.",
    "provider_error": "The AI provider returned a server error. Retry after checking its status page.",
    "endpoint_missing": "The provider endpoint was not found. This integration may need an updated API URL.",
    "invalid_response": "The provider replied, but did not return a valid chat completion. Check model and API compatibility.",
    "bad_request": "The provider rejected the verification request. Check the model and request compatibility.",
}


def provider_info(pid):
    v = _P.get(pid)
    return None if not v else {"id": pid, "label": v[0], "protocol": v[1],
                               "base_url": v[2], "default_model": v[3]}


def check_base_url(url):
    """Existing fail-closed SSRF guard for disabled-by-default custom providers."""
    try:
        u = urlparse(url or "")
    except Exception:
        return False, "Invalid URL."
    if (u.scheme != "https" or not u.hostname or u.username or u.password
            or u.query or u.fragment):
        return False, "Base URL must be a plain https:// address without credentials or query strings."
    host = u.hostname
    try:
        infos = socket.getaddrinfo(host, u.port or 443, proto=socket.IPPROTO_TCP)
    except Exception:
        return False, "Base URL host could not be resolved."
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved
                or ip.is_multicast or ip.is_unspecified):
            return False, "Base URL points to a private or internal address, which is not allowed."
    return True, ""


def _effective_base(provider, info, base_url):
    return (base_url or "").rstrip("/") if provider == "custom" else info["base_url"].rstrip("/")


def _headers(protocol, key):
    if protocol == "anthropic":
        return {"x-api-key": key, "anthropic-version": "2023-06-01",
                "content-type": "application/json", "accept": "application/json"}
    return {"Authorization": f"Bearer {key}", "content-type": "application/json",
            "accept": "application/json"}


def _error_content(resp):
    """Return only provider error category/message; never return entire payload or headers."""
    try:
        data = resp.json()
    except (ValueError, TypeError):
        return "", "", (resp.text or "")[:1000]
    if not isinstance(data, dict):
        return "", "", (resp.text or "")[:1000]
    error = data.get("error")
    if isinstance(error, dict):
        return (str(error.get("code") or ""), str(error.get("type") or ""),
                str(error.get("message") or "") or (resp.text or "")[:1000])
    if isinstance(error, str):
        return "", "", error
    return "", "", str(data.get("message") or "") or (resp.text or "")[:1000]


def _safe_hint(value, key):
    """Bound and redact provider-owned text before it reaches the admin UI."""
    hint = str(value or "")[:320]
    if key:
        hint = hint.replace(key, "[REDACTED]")
    hint = re.sub(r"(?i)bearer\s+\S+", "Bearer [REDACTED]", hint)
    hint = re.sub(r"(?i)(api[_ -]?key|token|authorization)\s*[:=]\s*[^ ,;\s]+",
                  r"\1=[REDACTED]", hint)
    hint = re.sub(r"\b(sk-[A-Za-z0-9_-]{8,}|AIza[A-Za-z0-9_-]{20,})\b", "[REDACTED]", hint)
    return hint.strip()


def _classify(status, body, provider_code="", provider_type=""):
    """Never confuse lack of permission/model access with a wrong API key."""
    text = " ".join((str(body or ""), str(provider_code or ""), str(provider_type or "")))
    if status in (200, 201):
        return "ok"
    if status == 402 or _CREDIT.search(text):
        return "no_credits"
    if status == 429:
        return "rate_limited"
    if status == 401 or _BADKEY.search(text):
        return "invalid_key"
    if _BADMODEL.search(text):
        return "bad_model"
    if status == 403 or _ACCESS.search(text):
        return "access_denied"
    if status == 404:
        return "endpoint_missing"
    if status >= 500:
        return "provider_error"
    return "bad_request"


def _outcome(code, provider, mdl, http_status=None, detail="", stage="inference"):
    return {"ok": code == "ok", "code": code, "message": MESSAGES[code],
            "provider": provider, "model": mdl, "stage": stage,
            "http_status": http_status, "detail": detail}


def validate_key(provider, api_key, model=None, base_url=None, timeout=25):
    """Verify a REAL chat completion, not just /models. No key is persisted here.

    The call is intentionally minimal but not 1-token (many models reject that).
    POST only; /models availability is not a reliable test across 25 vendors.
    """
    info = provider_info(provider)
    key = (api_key or "").strip()
    mdl = (model or (info["default_model"] if info else "") or "").strip()
    if not info:
        return {"ok": False, "code": "bad_request", "message": "Unknown AI provider."}
    if provider == "github":
        return {"ok": False, "code": "bad_request",
                "message": "GitHub Models was retired on July 30, 2026. Choose another AI provider."}
    if not key:
        return {"ok": False, "code": "invalid_key", "message": "Please enter the API key."}
    base = _effective_base(provider, info, base_url)
    if not base or not base.startswith("https://"):
        return {"ok": False, "code": "bad_request", "message": "A valid HTTPS provider URL is required."}
    if provider == "custom":
        if os.environ.get("BYOK_ALLOW_CUSTOM", "") != "1":
            return {"ok": False, "code": "bad_request",
                    "message": "Custom provider is disabled (BYOK_ALLOW_CUSTOM=1 is required)."}
        ok_url, why = check_base_url(base)
        if not ok_url:
            return {"ok": False, "code": "bad_request", "message": why}
    if not mdl:
        return {"ok": False, "code": "bad_model", "message": "Please enter a model name."}

    url = base + ("/messages" if info["protocol"] == "anthropic" else "/chat/completions")
    hdr = _headers(info["protocol"], key)
    body = {"model": mdl, "messages": [{"role": "user", "content": "Reply with OK."}],
            "max_tokens": 64}
    # Retry exactly once for models that reject the deprecated max_tokens field.
    try:
        resp = requests.post(url, headers=hdr, json=body, timeout=timeout, allow_redirects=False)
        if info["protocol"] != "anthropic" and resp.status_code == 400:
            ec, et, em = _error_content(resp)
            text = " ".join((ec, et, em)).lower()
            if "max_tokens" in text and "max_completion_tokens" in text:
                body.pop("max_tokens")
                body["max_completion_tokens"] = 64
                resp = requests.post(url, headers=hdr, json=body, timeout=timeout, allow_redirects=False)
    except requests.exceptions.SSLError:
        return _outcome("tls_error", provider, mdl, detail="HTTPS certificate validation failed")
    except (requests.exceptions.ConnectTimeout, requests.exceptions.ReadTimeout, requests.exceptions.Timeout):
        return _outcome("timeout", provider, mdl, detail="Request timed out at the server")
    except requests.exceptions.ProxyError:
        return _outcome("unreachable", provider, mdl, detail="Server proxy connection failed")
    except requests.exceptions.ConnectionError:
        return _outcome("unreachable", provider, mdl, detail="Server DNS, firewall, or TCP connection failed")
    except requests.exceptions.RequestException:
        return _outcome("unreachable", provider, mdl, detail="Server outbound HTTPS request failed")

    st = resp.status_code
    if st in (200, 201):
        if _is_real_completion(info["protocol"], resp):
            return _outcome("ok", provider, mdl, http_status=st, detail="Model responded to live inference")
        content_type = (resp.headers.get("content-type", "") if hasattr(resp, "headers") else "")
        return _outcome("invalid_response", provider, mdl, http_status=st,
                        detail="Expected chat JSON; received " + _safe_hint(content_type, key))

    ec, et, em = _error_content(resp)
    code = _classify(st, em, ec, et)
    # Only safe fragments are shown. Do not log provider response bodies or keys.
    hint_parts = [p for p in (ec, et, em) if p]
    hint = _safe_hint(" | ".join(hint_parts), key)
    if not hint:
        hint = "No structured provider error detail"  # never invent an invalid-key verdict
    return _outcome(code, provider, mdl, http_status=st, detail=hint)


def _is_real_completion(protocol, resp):
    try:
        j = resp.json()
    except (TypeError, ValueError):
        return False
    if not isinstance(j, dict):
        return False
    if protocol == "anthropic":
        return isinstance(j.get("content"), list) and len(j["content"]) > 0
    choices = j.get("choices")
    return (isinstance(choices, list) and bool(choices) and
            isinstance(choices[0], dict) and isinstance(choices[0].get("message"), dict))


def classify_runtime_error(exc):
    """Keep the existing BYOK runtime policy and avoid treating generic 403 as invalid keys."""
    text = f"{type(exc).__name__}: {exc}"
    st = getattr(exc, "status_code", None) or getattr(getattr(exc, "response", None), "status_code", None)
    if _CREDIT.search(text):
        return "no_credits"
    if st == 429 or re.search(r"\b429\b|rate.?limit|too many requests", text, re.I):
        return "rate_limited"
    if st == 401 or _BADKEY.search(text):
        return "invalid_key"
    if st == 403:
        return "access_denied"
    if _BADMODEL.search(text):
        return "bad_model"
    return None


def build_chat_model(provider, api_key, model=None, base_url=None):
    info = provider_info(provider)
    if not info:
        raise ValueError("Unknown AI provider")
    if provider == "github":
        raise ValueError("GitHub Models has been retired; please select a supported provider")
    mdl = model or info["default_model"]
    if info["protocol"] == "anthropic":
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(model=mdl, temperature=0, api_key=api_key)
    from langchain_openai import ChatOpenAI
    base = _effective_base(provider, info, base_url)
    if provider == "custom":
        if os.environ.get("BYOK_ALLOW_CUSTOM", "") != "1":
            raise ValueError("custom provider disabled")
        ok_url, why = check_base_url(base)
        if not ok_url:
            raise ValueError(why)
    return ChatOpenAI(model=mdl, temperature=0, api_key=api_key, base_url=base)


# ---- per-institution lookup (cached briefly; key stays encrypted at rest) ---------------------------
_cache, _lock, _TTL = {}, threading.Lock(), 300


def institution_ai_policy(client_prefix):
    """Read every institution-owned provider in priority order; never assume shared-AI consent.

    Reads only the AthenTech admin DB. An unavailable/malformed configuration
    fails closed instead of authorizing AthenTech spend.
    """
    if not client_prefix:
        raise ByokUnavailable("missing institution identity")
    try:
        from auth.institution_ai_slots import runtime_slots
        policy = runtime_slots(client_prefix)
    except Exception as exc:
        print(f"[byok] institution AI policy unavailable: {type(exc).__name__}", flush=True)
        raise ByokUnavailable("institution AI settings unreadable") from exc
    providers = policy["providers"]
    primary = providers[0] if providers else {}
    return {
        "provider": primary.get("provider"), "model": primary.get("model"),
        "api_key": primary.get("api_key"), "base_url": primary.get("base_url"),
        "providers": providers,
        "allow_athentech_fallback": bool(policy["allow_athentech_fallback"]),
    }


def institution_llm_settings(client_prefix):
    """Existing revalidation API: return own-key details only, or None when no key."""
    s = institution_ai_policy(client_prefix)
    return s if s["api_key"] else None


class ByokUnavailable(Exception):
    """Institution AI settings cannot be safely read or its configured model cannot run."""


class ByokOptInRequired(ByokUnavailable):
    """No institution key, and shared AthenTech AI has NOT been explicitly authorized."""


def institution_chain(client_prefix):
    """Choose client's own key or authorized shared AI; never assume consent.

    Returns None ONLY for the explicit allow_athentech_fallback=True, no-own-key
    case. All other missing-key situations fail closed.
    """
    if not client_prefix:
        raise ByokUnavailable("missing institution identity")
    now = time.time()
    with _lock:
        hit = _cache.get(str(client_prefix).upper())
        if hit and now - hit[0] < _TTL:
            if hit[1] == "blocked":
                raise ByokOptInRequired("institution AI not configured")
            return hit[1]
    try:
        s = institution_ai_policy(client_prefix)
    except ByokUnavailable:
        raise
    except Exception as e:
        print(f"[byok] cannot read institution AI policy: {type(e).__name__}", flush=True)
        raise ByokUnavailable("institution settings unreadable") from e

    # Older integrations and mock tests may return the legacy one-key
    # policy shape. Real production policies contain the full slots list.
    own_providers = s.get("providers")
    if own_providers is None:
        own_providers = [{"position": 1, "provider": s.get("provider"),
                          "api_key": s.get("api_key"), "model": s.get("model"),
                          "base_url": s.get("base_url")}] if s.get("api_key") else []
    if own_providers:
        chain = []
        for slot in own_providers:
            try:
                model = build_chat_model(slot["provider"], slot["api_key"], slot["model"], slot["base_url"])
                chain.append((slot["provider"] if slot["position"] == 1 else f"{slot['provider']}#slot{slot['position']}", model))
            except Exception as e:
                # A broken OPTIONAL client provider must not disable working
                # client-owned providers. Shared AthenTech AI remains forbidden.
                print(f"[byok] cannot build client provider slot {slot['position']}: {type(e).__name__}", flush=True)
                continue
        if not chain:
            raise ByokUnavailable("no institution provider could be built")
    elif s["allow_athentech_fallback"]:
        chain = None  # Only explicit no-key consent authorizes AthenTech AI.
    else:
        chain = "blocked"

    with _lock:
        _cache[str(client_prefix).upper()] = (now, chain)
    if chain == "blocked":
        raise ByokOptInRequired("institution AI not configured")
    return chain


def invalidate(client_prefix=None):
    with _lock:
        if client_prefix:
            _cache.pop(client_prefix, None)
        else:
            _cache.clear()
