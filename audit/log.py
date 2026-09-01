from datetime import datetime
import json
import os

os.makedirs("audit", exist_ok=True)

AUDIT_LOG_PATH = "audit/audit.log"


def audit(event: str, role: str = None, code: str = None, question: str = None, meta: dict = None):
    # Do NOT store full patient answers / PHI
    safe_question = (question or "")[:120]

    record = {
        "ts": datetime.utcnow().isoformat() + "Z",
        "event": event,
        "role": role,
        "code": code,
        "question": safe_question,
        "meta": meta or {}
    }

    with open(AUDIT_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


def read_audit_log(limit: int = 500) -> list:
    """
    Returns the most recent `limit` audit events, newest first.
    Malformed lines (e.g. from a crash mid-write) are skipped rather than
    failing the whole read — an audit page that 500s because of one bad
    line is worse than an audit page missing one event.
    """
    if not os.path.exists(AUDIT_LOG_PATH):
        return []

    records = []
    with open(AUDIT_LOG_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    records.reverse()  # newest first
    return records[:limit]