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
    "github":      ("GitHub Models", "openai", "https://models.inference.ai.azure.com", "gpt-4o-mini", "github.com/settings/tokens"),
    "huggingface": ("Hugging Face", "openai", "https://router.huggingface.co/v1", "meta-llama/Llama-3.3-70B-Instruct", "huggingface.co/settings/tokens"),
    "ai21":        ("AI21 Jamba", "openai", "https://api.ai21.com/studio/v1", "jamba-large", "studio.ai21.com"),
    "custom":      ("Other (OpenAI-compatible URL)", "openai", "", "", ""),
}

CATALOG = [{"id": k, "label": v[0], "base_url": v[2], "default_model": v[3], "key_page": v[4],
            "needs_base_url": k == "custom"} for k, v in _P.items()]

_CREDIT = re.compile(r"insufficient[_ ]?(quota|balance|funds|credit)|exceeded your current quota|credit balance|out of credit|no credits?|"
                     r"billing|payment required|balance is too low|quota (exceeded|exhausted)|resource_exhausted|not enough (credit|balance)|"
                     r"top.?up|add (a )?payment|exhausted", re.I)
_BADKEY = re.compile(r"invalid[_ ]?(api)?[_ ]?key|incorrect api key|unauthorized|authentication|invalid x-api-key|api key not valid|"
                     r"permission_denied|invalid token|bad credentials|unauthenticated|api_key_invalid", re.I)
_BADMODEL = re.compile(r"model.{0,40}(not found|does not exist|not supported|unknown|decommission)|no such model|invalid model", re.I)

MESSAGES = {
    "ok": "API key verified.",
    "invalid_key": "Incorrect API key. Please check the key and the selected provider.",
    "no_credits": "The key is correct, but this account has no credits or tokens left. Please top up the provider account.",
    "rate_limited": "The key is correct, but the provider is rate-limiting it right now. Please try again in a minute.",
    "bad_model": "The key looks valid, but the selected model was not found for this account. Choose another model.",
    "unreachable": "Could not reach the provider to verify the key. Please try again.",
    "bad_request": "The provider rejected the verification request. Check the provider, model and URL.",
}


def provider_info(pid):
    v = _P.get(pid)
    return None if not v else {"id": pid, "label": v[0], "protocol": v[1], "base_url": v[2], "default_model": v[3]}


def check_base_url(url):
    """SSRF guard for user-supplied URLs ('custom' provider): https only, no credentials in URL, and the host must
    not resolve to loopback / private / link-local / reserved addresses (blocks internal services and cloud metadata)."""
    try:
        u = urlparse(url or "")
    except Exception:
        return False, "Invalid URL."
    if u.scheme != "https" or not u.hostname or u.username or u.password:
        return False, "Base URL must be a plain https:// address."
    host = u.hostname
    try:
        infos = socket.getaddrinfo(host, u.port or 443, proto=socket.IPPROTO_TCP)
    except Exception:
        return False, "Base URL host could not be resolved."
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
            return False, "Base URL points to a private or internal address, which is not allowed."
    return True, ""


def _effective_base(provider, info, base_url):
    """Only the 'custom' provider may use a user-supplied URL; every other provider is pinned to its catalog URL."""
    return (base_url or "").rstrip("/") if provider == "custom" else info["base_url"].rstrip("/")


def _classify(status, body):
    text = str(body or "")[:1500]
    if status == 200:
        return "ok"
    if _CREDIT.search(text) or status == 402:
        return "no_credits"
    if status in (401, 403) or _BADKEY.search(text):
        return "invalid_key"
    if status == 429:
        return "rate_limited"
    if _BADMODEL.search(text) or status == 404:
        return "bad_model"
    if status >= 500:
        return "unreachable"
    return "bad_request"


def _headers(protocol, key):
    if protocol == "anthropic":
        return {"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"}
    return {"Authorization": f"Bearer {key}", "content-type": "application/json"}


def validate_key(provider, api_key, model=None, base_url=None, timeout=20):
    """Returns {ok, code, message}. Step 1 lists models (costs nothing) to catch wrong keys;
    step 2 sends a 1-token chat so 'no credits' is detected too. Key is never logged or returned."""
    info = provider_info(provider)
    key = (api_key or "").strip()
    if not info:
        return {"ok": False, "code": "bad_request", "message": "Unknown AI provider."}
    if not key:
        return {"ok": False, "code": "invalid_key", "message": "Please enter the API key."}
    base = _effective_base(provider, info, base_url)
    mdl = (model or info["default_model"] or "").strip()
    if not base or not re.match(r"^https://", base):
        return {"ok": False, "code": "bad_request", "message": "A valid https:// base URL is required."}
    if provider == "custom":
        if os.environ.get("BYOK_ALLOW_CUSTOM", "") != "1":
            return {"ok": False, "code": "bad_request",
                    "message": "The 'Other (custom URL)' provider is disabled on this server (set BYOK_ALLOW_CUSTOM=1 to enable)."}
        ok_url, why = check_base_url(base)
        if not ok_url:
            return {"ok": False, "code": "bad_request", "message": why}
    if not mdl:
        return {"ok": False, "code": "bad_model", "message": "Please enter the model name."}
    hdr = _headers(info["protocol"], key)
    try:
        r = requests.get(base + "/models", headers=hdr, timeout=timeout, allow_redirects=False)
        if r.status_code in (401, 403) or (r.status_code != 200 and _BADKEY.search(r.text or "")):
            code = _classify(r.status_code, r.text)
            if code == "invalid_key":
                return {"ok": False, "code": code, "message": MESSAGES[code]}
        if info["protocol"] == "anthropic":
            url = base + "/messages"
            body = {"model": mdl, "max_tokens": 1, "messages": [{"role": "user", "content": "hi"}]}
        else:
            url = base + "/chat/completions"
            body = {"model": mdl, "max_tokens": 1, "messages": [{"role": "user", "content": "hi"}]}
        r = requests.post(url, headers=hdr, json=body, timeout=timeout, allow_redirects=False)
        if r.status_code == 400 and "max_tokens" in (r.text or "") and "max_completion_tokens" in (r.text or ""):
            body.pop("max_tokens"); body["max_completion_tokens"] = 16
            r = requests.post(url, headers=hdr, json=body, timeout=timeout, allow_redirects=False)
        code = _classify(r.status_code, r.text)
        if code == "ok" and not _is_real_completion(info["protocol"], r):
            code = "bad_request"
        return {"ok": code == "ok", "code": code, "message": MESSAGES[code]}
    except requests.exceptions.RequestException:
        return {"ok": False, "code": "unreachable", "message": MESSAGES["unreachable"]}


def _is_real_completion(protocol, resp):
    """HTTP 200 alone is not proof: require a genuine model reply shape."""
    try:
        j = resp.json()
    except Exception:
        return False
    if protocol == "anthropic":
        return isinstance(j, dict) and isinstance(j.get("content"), list)
    ch = j.get("choices") if isinstance(j, dict) else None
    return isinstance(ch, list) and len(ch) > 0 and isinstance(ch[0], dict) and "message" in ch[0]


def classify_runtime_error(exc):
    """Map an exception raised during a live chat call to a BYOK code, or None if unrelated."""
    text = f"{type(exc).__name__}: {exc}"
    st = getattr(exc, "status_code", None) or getattr(getattr(exc, "response", None), "status_code", None)
    if _CREDIT.search(text):
        return "no_credits"
    if st in (401, 403) or _BADKEY.search(text):
        return "invalid_key"
    if st == 429 or re.search(r"rate.?limit|too many requests|429", text, re.I):
        return "rate_limited"
    return None


def build_chat_model(provider, api_key, model=None, base_url=None):
    info = provider_info(provider)
    if not info:
        raise ValueError("Unknown AI provider")
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


def institution_llm_settings(client_prefix):
    """Decrypted BYOK settings for an institution, or None if it has no key configured."""
    if not client_prefix:
        return None
    from database.license_db import get_conn
    from auth.secrets_crypto import decrypt_secret
    conn = get_conn()
    try:
        row = conn.execute("SELECT llm_provider, llm_model, llm_api_key, llm_base_url FROM institutions "
                           "WHERE client_prefix = ?", (str(client_prefix).upper(),)).fetchone()
    finally:
        conn.close()
    if not row or not row["llm_api_key"] or not row["llm_provider"]:
        return None
    return {"provider": row["llm_provider"], "model": row["llm_model"] or None,
            "api_key": decrypt_secret(row["llm_api_key"]), "base_url": row["llm_base_url"] or None}


class ByokUnavailable(Exception):
    """The institution HAS its own AI key configured but it can't be used right now (settings unreadable /
    model can't be built). Callers must NOT fall back to AthenTech's shared AI."""


def institution_chain(client_prefix):
    """[(provider, model)] for this institution's own key, or None if it has NO own key (use AthenTech's chain).
    Raises ByokUnavailable when a key is configured/possibly configured but cannot be used: fail closed."""
    now = time.time()
    with _lock:
        hit = _cache.get(client_prefix)
        if hit and now - hit[0] < _TTL:
            return hit[1]
    try:
        s = institution_llm_settings(client_prefix)
    except Exception as e:
        # Columns not migrated yet => nobody has a key => shared AI. Anything else (DB down, decrypt error): fail closed.
        if re.search(r"invalid column name|42s22", str(e), re.I):
            try:
                from database import byok_migration
                migrated = byok_migration.READY
            except Exception:
                migrated = False
            if not migrated:          # migration never completed => nobody can have a key yet => shared AI
                return None
            # migration said OK but columns are gone/inconsistent: fail closed
            raise ByokUnavailable("settings schema inconsistent") from e
        print(f"[byok] cannot read institution key settings: {type(e).__name__}", flush=True)
        raise ByokUnavailable("settings unreadable") from e
    if not s:
        chain = None
    else:
        try:
            chain = [(s["provider"], build_chat_model(s["provider"], s["api_key"], s["model"], s["base_url"]))]
        except Exception as e:
            print(f"[byok] cannot build model for institution: {type(e).__name__}", flush=True)
            raise ByokUnavailable("model unavailable") from e
    with _lock:
        _cache[client_prefix] = (now, chain)
    return chain


def invalidate(client_prefix=None):
    with _lock:
        if client_prefix:
            _cache.pop(client_prefix, None)
        else:
            _cache.clear()
