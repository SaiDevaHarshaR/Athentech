"""Makes a model request fit a provider's size limit (e.g. Groq free/on-demand: 8,000 tokens per request).
compress(messages, max_chars) shortens the least important parts first: old tool results, helper notes, chat history, then the middle of the
main instructions. The user's question and the newest tool results are kept. Never raises: on any problem the original list is returned."""
import os

SMALL = {p.strip() for p in os.getenv("SAHASRA_SMALL_TPM_PROVIDERS", "groq").split(",") if p.strip()}
BUDGET = int(os.getenv("SAHASRA_SMALL_PROMPT_CHARS", "8500"))      # about 5,000 tokens, leaving room for the tool list and the answer


def _text(m):
    c = getattr(m, "content", "")
    return c if isinstance(c, str) else str(c)


def _size(msgs):
    return sum(len(_text(m)) for m in msgs)


def _with(m, text):
    try:
        return m.model_copy(update={"content": text})
    except Exception:
        try:
            return m.copy(update={"content": text})
        except Exception:
            return m


def _cut(t, n, tail=0):
    if len(t) <= n:
        return t
    if tail:
        return t[: n - tail - 20] + "\n...[shortened]...\n" + t[-tail:]
    return t[:n] + " ...[shortened]"


def compress(messages, max_chars=None):
    try:
        max_chars = max_chars or BUDGET
        msgs = list(messages)
        if _size(msgs) <= max_chars:
            return messages
        kind = lambda m: type(m).__name__
        last_h = max([i for i, m in enumerate(msgs) if kind(m) == "HumanMessage"] or [-1])
        tools = [i for i, m in enumerate(msgs) if kind(m) == "ToolMessage"]
        # 1) tool results: newest two keep 900 characters, older ones 300
        for n, i in enumerate(reversed(tools)):
            msgs[i] = _with(msgs[i], _cut(_text(msgs[i]), 900 if n < 2 else 300))
        if _size(msgs) <= max_chars:
            return msgs
        # 2) chat history before the current question: 300 characters each
        for i, m in enumerate(msgs):
            if i < last_h and kind(m) in ("HumanMessage", "AIMessage"):
                msgs[i] = _with(m, _cut(_text(m), 300))
        if _size(msgs) <= max_chars:
            return msgs
        # 3) helper system notes (everything except the first = main instructions)
        sys_idx = [i for i, m in enumerate(msgs) if kind(m) == "SystemMessage"]
        for i in sys_idx[1:]:
            t = _text(msgs[i])
            cap = 2200 if t.startswith("ANSWER INTEGRITY") else 1600
            msgs[i] = _with(msgs[i], _cut(t, cap))
        if _size(msgs) <= max_chars:
            return msgs
        # 4) main instructions: keep the start (rules) and the end (efficiency rules), cut the middle
        if sys_idx:
            i = sys_idx[0]
            room = max(4000, max_chars - (_size(msgs) - len(_text(msgs[i]))))
            msgs[i] = _with(msgs[i], _cut(_text(msgs[i]), room, tail=min(1800, room // 3)))
        return msgs
    except Exception:
        return messages
