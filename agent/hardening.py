"""Hardening, attached by agent.guard_hooks.install():
  * rate limits on the public endpoints (per visitor IP, sliding 60 s window) - a flood gets a polite 429 instead of draining AI credit
  * log redaction - API keys, bearer tokens and passwords are masked in everything printed to the service log
Tune with env:  SAHASRA_RATE_LIMIT=0 (off)   SAHASRA_RATE_ASK=120   SAHASRA_RATE_LOGIN=10   SAHASRA_RATE_PUBLIC=30   SAHASRA_TRUST_PROXY=0 (ignore X-Forwarded-For)"""
import json
import os
import re
import sys
import threading
import time
from collections import defaultdict, deque

_LOCK = threading.Lock()
_HITS = defaultdict(deque)
_LAST_PRUNE = [0.0]


def _limits():
    g = lambda k, d: int(os.getenv(k, d) or d)
    ask, login, pub = g("SAHASRA_RATE_ASK", 120), g("SAHASRA_RATE_LOGIN", 10), g("SAHASRA_RATE_PUBLIC", 30)
    return [  # (method, path prefix, bucket, per-minute)
        ("POST", "/ask", "ask", ask),
        ("POST", "/verify-otp", "otp", 10),
        ("POST", "/admin/login", "login", login),
        ("POST", "/public/b2b/request-otp", "b2botp", 10),
        ("POST", "/public/b2b/verify-otp", "b2bver", 20),
        ("POST", "/public/whitelabel-ask", "wlask", pub),
        ("POST", "/public/b2b/chat", "b2bchat", pub),
    ]


def _ip(scope):
    ip = (scope.get("client") or ("unknown", 0))[0]
    if os.getenv("SAHASRA_TRUST_PROXY", "1") != "0":
        for k, v in scope.get("headers") or []:
            if k == b"x-forwarded-for":
                first = v.decode("latin-1").split(",")[0].strip()
                if first:
                    ip = first[:64]
                break
    return ip


def allow(ip, bucket, limit, now=None):
    now = now or time.time()
    with _LOCK:
        q = _HITS[(ip, bucket)]
        while q and now - q[0] > 60:
            q.popleft()
        if len(q) >= limit:
            return False, max(1, int(60 - (now - q[0])))
        q.append(now)
        if now - _LAST_PRUNE[0] > 300:
            _LAST_PRUNE[0] = now
            for k in [k for k, v in _HITS.items() if not v or now - v[-1] > 120]:
                _HITS.pop(k, None)
    return True, 0


class RateLimit:
    def __init__(self, app):
        self.app = app
        self.rules = _limits()

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or os.getenv("SAHASRA_RATE_LIMIT", "1") == "0":
            return await self.app(scope, receive, send)
        method, path = scope.get("method"), scope.get("path", "")
        for m, prefix, bucket, limit in self.rules:
            if method == m and (path == prefix or path.startswith(prefix + "/")):
                ok, wait = allow(_ip(scope), bucket, limit)
                if not ok:
                    body = json.dumps({"status": "error", "answer": "You're sending requests too quickly. Please wait %d seconds and try again." % wait,
                                       "message": "Too many requests."}).encode()
                    await send({"type": "http.response.start", "status": 429, "headers": [
                        (b"content-type", b"application/json"), (b"retry-after", str(wait).encode()), (b"content-length", str(len(body)).encode())]})
                    return await send({"type": "http.response.body", "body": body})
                break
        return await self.app(scope, receive, send)


# ----------------------------------------------------------------------------- log redaction
_PATTERNS = [
    re.compile(r"\bgsk_[A-Za-z0-9]{20,}"), re.compile(r"\bsk-[A-Za-z0-9_\-]{20,}"), re.compile(r"\bsk-or-[A-Za-z0-9_\-]{20,}"),
    re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._\-]{20,}"),
    re.compile(r"(?i)((?:api[_-]?key|apikey|secret|token|password|passwd|pwd)[\"']?\s*[:=]\s*[\"']?)[^\s\"',;&}]{6,}"),
    re.compile(r"(?i)(PWD=)[^;\s]+"),
]


def redact(text, extra=()):
    if not text:
        return text
    for p in _PATTERNS:
        text = p.sub(lambda m: (m.group(1) if m.lastindex else "") + "***", text) if p.groups else p.sub("***", text)
    for v in extra:
        if v in text:
            text = text.replace(v, "***")
    return text


def _secret_values():
    out = []
    for k, v in os.environ.items():
        if v and len(v) >= 8 and re.search(r"KEY|SECRET|TOKEN|PASSWORD|PASSWD", k, re.I) and not re.fullmatch(r"[0-9.]+|true|false", v, re.I):
            out.append(v)
    return out


class _Redacting:
    def __init__(self, stream):
        self._s = stream
        self._extra = _secret_values()

    def write(self, data):
        try:
            return self._s.write(redact(data, self._extra) if isinstance(data, str) else data)
        except Exception:
            return self._s.write(data)

    def __getattr__(self, name):
        return getattr(self._s, name)


def install_redaction():
    for name in ("stdout", "stderr"):
        st = getattr(sys, name, None)
        if st is not None and not isinstance(st, _Redacting):
            setattr(sys, name, _Redacting(st))


def install(app):
    try:
        app.add_middleware(RateLimit)
    except Exception as e:
        print("[hardening] rate limit not installed:", type(e).__name__)
    try:
        install_redaction()
    except Exception as e:
        print("[hardening] log redaction not installed:", type(e).__name__)
