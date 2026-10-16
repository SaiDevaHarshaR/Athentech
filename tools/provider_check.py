"""Why does the log say "client provider #1 (groq) failed: APIStatusError"?   python tools\\provider_check.py
Calls every AI provider once with a tiny message, then once with a big one (~24,000 characters, like a real data question),
and prints the real error (status code + message) instead of just the class name. Costs a few tokens. Read-only."""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass
from langchain_core.messages import HumanMessage, SystemMessage
from agent.agent import _get_provider_chain


def why(e):
    code = getattr(e, "status_code", None) or getattr(getattr(e, "response", None), "status_code", None)
    body = ""
    try:
        body = str(getattr(e, "body", "") or getattr(getattr(e, "response", None), "text", "") or e)
    except Exception:
        body = repr(e)
    hdr = {}
    try:
        h = getattr(getattr(e, "response", None), "headers", {}) or {}
        hdr = {k: h[k] for k in h if k.lower().startswith(("retry-after", "x-ratelimit"))}
    except Exception:
        pass
    return "%s status=%s %s %s" % (type(e).__name__, code, body[:400].replace("\n", " "), hdr or "")


chain = _get_provider_chain()
if not chain:
    print("No AI provider is configured.")
for name, model in chain:
    for label, text in (("small (20 chars)", "Reply with the word OK."), ("big (~24,000 chars)", "Reply with the word OK. Ignore this filler: " + ("lorem ipsum dolor sit amet " * 890))):
        t = time.time()
        try:
            r = model.invoke([SystemMessage(content="You are a test."), HumanMessage(content=text)])
            print("%-12s %-22s OK in %.1fs: %s" % (name, label, time.time() - t, str(getattr(r, "content", r))[:40].strip()))
        except Exception as e:
            print("%-12s %-22s FAILED in %.1fs: %s" % (name, label, time.time() - t, why(e)))
        time.sleep(1)
