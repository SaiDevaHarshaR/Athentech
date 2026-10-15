"""Self-check for AI answers: figures not found in the database results get ONE corrective pass.

Pure helpers + one function that takes the model call as a callable, so it is testable offline.
Never raises; on any problem the original answer is returned unchanged."""
from __future__ import annotations

from agent import confidence as _c

MAX_FIGURES_SHOWN = 6


def find_ungrounded(answer, ok_results, question=""):
    """Figures in the answer that appear in no tool result (and not in the question itself)."""
    if not answer or not ok_results:
        return [], 0
    pool = []
    for r in ok_results:
        pool += _c._numbers(str(r))
    qn = set(_c._numbers(question))
    claims = [v for v in _c._numbers(answer) if v not in qn]
    return [v for v in claims if not _c._grounded(v, pool)], len(claims)


def needs_repair(missing, total_claims):
    """Repair only when it is clearly worth an extra model call: >=2 unsupported figures, or most of them."""
    if not missing:
        return False
    return len(missing) >= 2 or (total_claims and len(missing) / total_claims >= 0.5)


def _fmt(v):
    return f"{v:,.0f}" if float(v).is_integer() else f"{v:,.2f}"


def repair_prompt(missing):
    shown = ", ".join(_fmt(v) for v in missing[:MAX_FIGURES_SHOWN])
    return ("Check your answer against the tool results above. These figures do not appear in any tool result: "
            f"{shown}. For each one: if you calculated it, keep it and state the calculation in a few words using "
            "figures from the results; otherwise remove it or say the value could not be verified. "
            "Do not add any new figures. Reply with the corrected answer only, in the same format and language.")


def maybe_repair(answer, ok_results, question, ask_model):
    """ask_model(prompt:str) -> str|None. Returns (answer, repaired:bool)."""
    try:
        missing, total = find_ungrounded(answer, ok_results, question)
        if not needs_repair(missing, total):
            return answer, False
        fixed = ask_model(repair_prompt(missing))
        if not fixed or not str(fixed).strip():
            return answer, False
        fixed = str(fixed).strip()
        left, _ = find_ungrounded(fixed, ok_results, question)
        # accept only if it did not get worse and is not a degenerate reply
        if len(left) < len(missing) and len(fixed) >= 0.3 * len(answer):
            return fixed, True
        return answer, False
    except Exception:
        return answer, False
