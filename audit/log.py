from datetime import datetime
import json
import os

os.makedirs("audit", exist_ok=True)

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

    with open("audit/audit.log", "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")