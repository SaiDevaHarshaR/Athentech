"""Privacy-safe Sahasra metrics. No patient, phone, code, message, tenant, URL, or SQL labels.

Disabled by default. To enable, set SAHASRA_METRICS_ENABLED=1 and a strong
SAHASRA_METRICS_TOKEN. HTTP requests to the internal scrape endpoint require
Authorization: Bearer <token>. Fail closed if token is missing.
"""
import hmac
import os
import re
import time
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from starlette.responses import PlainTextResponse, Response

METRICS_PATH = "/internal/metrics"
_HTTP = Counter("sahasra_http_requests_total", "HTTP request count by coarse route class", ["route", "method", "status_class"])
_LATENCY = Histogram("sahasra_http_request_seconds", "HTTP request duration", ["route", "method"], buckets=(.005,.01,.025,.05,.1,.25,.5,1,2.5,5,10,30,60))
_B2B = Counter("sahasra_b2b_requests_total", "B2B endpoint requests; HTTP status-class only", ["operation", "status_class"])
_EXPORT = Histogram("sahasra_report_request_seconds", "Report request processing seconds", ["format", "status_class"], buckets=(.05,.1,.25,.5,1,2.5,5,15,30,60))
_AI_REQUESTS = Counter("sahasra_ai_provider_attempts_total", "Explicit AI provider attempts, never credentials or tenant labels", ["provider", "result"])
_AI_SECONDS = Histogram("sahasra_ai_provider_seconds", "Explicit AI provider call latency", ["provider"], buckets=(.05,.1,.25,.5,1,2.5,5,10,30,60))
_OTP = Counter("sahasra_b2b_otp_outcomes_total", "Explicit B2B OTP outcomes, never phone or organization labels", ["action", "result"])

_ALLOWED_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"}
_ALLOWED_PROVIDERS = {"openai","gemini","anthropic","groq","mistral","cohere","openrouter","together","fireworks","deepseek","xai","cerebras","sambanova","deepinfra","nvidia","hyperbolic","novita","moonshot","zhipu","qwen","siliconflow","huggingface","ai21"}
_B2B_ROUTES = {
    "/public/b2b/request-otp": "otp_request",
    "/public/b2b/verify-otp": "otp_verify",
    "/public/b2b/overview": "overview",
    "/public/b2b/bills": "bills",
    "/public/b2b/download-excel": "excel_download",
    "/public/b2b/chat": "chat",
    "/public/b2b/logout": "logout",
}
_REPORT_PATHS = {"/generate-excel":"excel","/generate-pdf":"pdf","/generate-patient-report":"pdf"}


def _route(path):
    if path in _B2B_ROUTES: return "b2b_" + _B2B_ROUTES[path]
    if re.fullmatch(r"/public/b2b/patient-report/[^/]+", path): return "b2b_pdf_download"
    if path in _REPORT_PATHS: return "report_" + _REPORT_PATHS[path]
    if path == "/ask": return "ask"
    if path == "/health": return "health"
    if path == "/public-config": return "public_config"
    if path.startswith("/admin/"): return "admin_other"
    if path.startswith("/widget"): return "widget_other"
    return "other"


def _status_class(status):
    return str(status // 100) + "xx" if 100 <= status < 600 else "unknown"


def record_ai_provider(provider, result, elapsed_seconds=None):
    """Call ONLY from a provider adapter's actual network-call completion.

    Not automatically wired to legacy/multi-BYOK adapters; explicit hooks
    avoid inaccurate attribution or silently changing provider selection.
    """
    p = str(provider).strip().lower().replace(" ", "")
    if p not in _ALLOWED_PROVIDERS: p = "other"
    result = result if result in {"success","error","timeout","rate_limited","quota_exhausted","invalid_key"} else "other_error"
    _AI_REQUESTS.labels(p, result).inc()
    if elapsed_seconds is not None and isinstance(elapsed_seconds,(int,float)) and 0 <= elapsed_seconds < 3600:
        _AI_SECONDS.labels(p).observe(elapsed_seconds)


def record_b2b_otp_outcome(action, result):
    """Call from OTP backend only after the outcome is known, never before."""
    if action not in {"request", "verify"}: return
    if result not in {"sent","accepted","success","invalid","rate_limited","error"}: return
    _OTP.labels(action, result).inc()


def _enabled():
    return os.getenv("SAHASRA_METRICS_ENABLED", "0").strip().lower() in ("1", "true", "yes")


def _authenticated(request):
    token = os.getenv("SAHASRA_METRICS_TOKEN", "")
    if not _enabled() or len(token) < 32: return False
    value = request.headers.get("authorization", "")
    return value.startswith("Bearer ") and hmac.compare_digest(value[7:], token)


async def metrics_middleware(request, call_next):
    path = request.url.path
    if path == METRICS_PATH:
        if not _authenticated(request):
            return PlainTextResponse("Not found", status_code=404, headers={"Cache-Control":"no-store"})
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST,
                        headers={"Cache-Control":"no-store","X-Content-Type-Options":"nosniff"})
    start = time.perf_counter()
    route = _route(path)
    method = request.method if request.method in _ALLOWED_METHODS else "OTHER"
    code = 500
    try:
        response = await call_next(request)
        code = response.status_code
        return response
    finally:
        elapsed = max(0, time.perf_counter() - start)
        cls = _status_class(code)
        _HTTP.labels(route, method, cls).inc()
        _LATENCY.labels(route, method).observe(elapsed)
        op = _B2B_ROUTES.get(path)
        if not op and route == "b2b_pdf_download": op = "pdf_download"
        if op: _B2B.labels(op, cls).inc()
        fmt = _REPORT_PATHS.get(path)
        if fmt is None and op in {"excel_download", "pdf_download"}:
            fmt = "excel" if op == "excel_download" else "pdf"
        if fmt is not None: _EXPORT.labels(fmt, cls).observe(elapsed)
