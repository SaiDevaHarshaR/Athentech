"""Opt-in metadata-only Langfuse observations. No prompts, messages or identifiers.

Designed for Langfuse Python SDK v4. Do not install global LangChain callback
handlers or @observe(capture_input=True) in a healthcare application.
"""
import functools
import os
import re
from contextlib import contextmanager

_TRUE = {"1", "true", "yes", "on"}
_SAFE_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,63}$")
_CLIENT = None


def enabled():
    return os.getenv("SAHASRA_LANGFUSE_ENABLED", "0").strip().lower() in _TRUE


def _safe_label(value, default="unspecified"):
    if isinstance(value, str) and _SAFE_NAME.fullmatch(value):
        return value
    return default


def _client():
    """No SDK initialization until explicitly enabled and fully configured."""
    global _CLIENT
    if not enabled():
        return None
    if not all(os.getenv(k) for k in ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_BASE_URL")):
        return None
    if _CLIENT is None:
        try:
            from langfuse import get_client
            _CLIENT = get_client()
        except Exception:
            return None
    return _CLIENT


@contextmanager
def observation(name, metadata=None, kind="span"):
    """Observation failure never blocks user operations.

    Exceptions from wrapped work are intercepted inside observation lifetime
    so the OTel context manager never sees exception text or traceback.
    We then re-raise the original outside the scope.
    """
    client = _client()
    if client is None:
        yield None
        return
    try:
        scope = client.start_as_current_observation(
            name=_safe_label(name, "operation"),
            as_type=kind,
            metadata=metadata or {},
        )
        span = scope.__enter__()
    except Exception:
        yield None
        return
    try:
        yield span
    finally:
        try:
            # No exception details leave the app through the span exit.
            scope.__exit__(None, None, None)
        except Exception:
            pass


def _finish(span, *, success, tokens=None):
    if span is None:
        return
    try:
        payload = {"outcome": "ok" if success else "error"}
        if isinstance(tokens, int) and 0 <= tokens <= 10000000:
            payload["total_tokens"] = tokens
        span.update(metadata=payload, level="DEFAULT" if success else "ERROR")
    except Exception:
        pass


def trace_agent_call(fn):
    """Decorates ask_agent; observes mode and numeric usage only."""
    @functools.wraps(fn)
    def wrapped(*args, **kwargs):
        # Signature on latest BYOK versions is *args/**kwargs; fields may be absent.
        premium = kwargs.get("is_premium", False)
        meta = {"operation": "agent", "mode": "premium" if premium else "standard"}
        with observation("sahasra.agent", meta, "agent") as span:
            try:
                result = fn(*args, **kwargs)
            except BaseException:
                _finish(span, success=False)
                raise
            _finish(span, success=True, tokens=(result[1] if isinstance(result, tuple) and len(result)>1 and isinstance(result[1], int) else None))
            return result
    return wrapped


def trace_llm_call(fn):
    """Decorates _invoke_with_retry; does NOT observe messages or response.

    No provider identifier inferred from runnable repr (may contain secrets).
    A caller-supplied provider name is accepted only if a short safe slug.
    """
    @functools.wraps(fn)
    def wrapped(*args, **kwargs):
        provider = _safe_label(kwargs.get("current_provider", "unspecified"))
        meta = {"operation": "llm_attempt", "provider": provider}
        with observation("sahasra.llm", meta, "generation") as span:
            try:
                result = fn(*args, **kwargs)
            except BaseException:
                _finish(span, success=False)
                raise
            # Return None is an exhausted-provider state, not a success.
            tokens = None
            usage = getattr(result, "usage_metadata", None)
            if isinstance(usage, dict):
                val=usage.get("total_tokens")
                tokens = val if type(val) is int else None
            _finish(span, success=result is not None, tokens=tokens)
            return result
    return wrapped


def trace_business_operation(name, operation):
    """For integration into authorized B2B handlers, AFTER auth checks.

    operation: zero-arg callable. No body, result, phone, bill or org codes sent.
    """
    with observation("sahasra.b2b", {"operation": _safe_label(name)}) as span:
        try:
            result = operation()
        except BaseException:
            _finish(span, success=False)
            raise
        _finish(span, success=True)
        return result
