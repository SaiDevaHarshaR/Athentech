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

def check_input(text: str) -> tuple[bool, str]:
    t = text.lower().strip()

    for pattern in BLOCKED_PATTERNS:
        if re.search(pattern, t, re.IGNORECASE):
            return False, "I can’t process that request."

    for topic in DISALLOWED_TOPICS:
        if topic in t:
            return False, "I can’t help with that topic."

    return True, ""

def check_output(text: str) -> str:
    # Basic redaction example
    text = re.sub(r"\b\d{3}-\d{2}-\d{4}\b", "[REDACTED]", text)
    return text