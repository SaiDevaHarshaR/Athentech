import re

BLOCKED_PATTERNS = [
    r"ignore (all )?(previous|above) instructions",
    r"jailbreak",
    r"dan mode",
    r"developer mode",
    r"bypass (the )?filter",
    r"pretend you are",
    r"act as if you have no restrictions",
]

SENSITIVE_OUTPUT_PATTERNS = [
    r"\b\d{3}-\d{2}-\d{4}\b",          # SSN-like
    r"\b(?:\d[ -]*?){13,16}\b",        # credit card-like
]

DISALLOWED_TOPICS = [
    "how to hack",
    "make a bomb",
    "buy illegal",
]


def _extra_blocked_patterns() -> list:
    """
    Admin-configurable patterns from the Settings page, layered on top of
    the built-in list above (never replaces it). Lazy import to avoid a
    circular import (license_service -> database -> ... never imports
    guardrails, so this direction is safe).
    """
    try:
        from auth.license_service import get_settings
        return get_settings().get("extra_blocked_patterns", [])
    except Exception:
        # Settings DB not reachable for some reason — fail open on the
        # extra patterns (built-in patterns below still apply) rather
        # than breaking every chat request.
        return []


def check_input(text: str) -> tuple[bool, str]:
    t = text.lower().strip()

    for pattern in BLOCKED_PATTERNS:
        if re.search(pattern, t, re.IGNORECASE):
            return False, "I can’t process that request."

    for pattern in _extra_blocked_patterns():
        try:
            if re.search(pattern, t, re.IGNORECASE):
                return False, "I can’t process that request."
        except re.error:
            continue  # an admin typed an invalid regex — skip it, don't crash requests

    for topic in DISALLOWED_TOPICS:
        if topic in t:
            return False, "I can’t help with that topic."

    return True, ""


def check_output(text: str) -> str:
    try:
        from auth.license_service import get_settings
        redaction_enabled = get_settings().get("output_redaction_enabled", True)
    except Exception:
        redaction_enabled = True  # fail safe: redact by default if settings can't be read

    if not redaction_enabled:
        return text

    text = re.sub(r"\b\d{3}-\d{2}-\d{4}\b", "[REDACTED]", text)
    return text