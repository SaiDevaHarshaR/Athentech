"""
Chip health: only ever suggest a chip that is answered INSTANTLY (no LLM) with real content on THIS institution's data.

How: each chip is run through the real ask_agent() in a "no-LLM" mode (a context variable that makes the single LLM
entry point raise NeedsLLM). The mode is per-thread, so it can never affect a real user's request. Outcomes are
cached per institution+role for hours. A chip that would need the LLM, errors, is blocked for the role, or comes back
empty is hidden from the suggestions. Costs zero tokens.
"""
import contextvars
import re
import threading
import time

NO_LLM = contextvars.ContextVar("sahasra_no_llm", default=False)


class NeedsLLM(BaseException):
    """Raised (only in no-LLM mode) when answering would require the LLM. BaseException so no handler swallows it."""


_TTL_OK, _TTL_PARTIAL = 12 * 3600, 2 * 3600
_cache, _running = {}, set()
_lock = threading.Lock()
_BAD_TEXT = re.compile(r"^(error\b|could not|couldn't|sorry|your role|you do not have|not available|no llm|i could not)", re.I)
_EMPTY_TEXT = re.compile(r"^(no |nothing |0 )", re.I)


def classify(answer):
    """-> (ok, reason)"""
    if answer is None or not str(answer).strip():
        return False, "no answer"
    a = str(answer).strip()
    if _BAD_TEXT.search(a):
        return False, "error/denied: " + a[:60]
    if _EMPTY_TEXT.search(a) and "```" not in a:
        return False, "empty result"
    return True, "ok"


def check_one(ask_fn, chip):
    token = NO_LLM.set(True)
    try:
        return classify(ask_fn(chip))
    except NeedsLLM:
        return False, "would need the LLM"
    except Exception as e:
        return False, f"{type(e).__name__}: {str(e)[:60]}"
    finally:
        NO_LLM.reset(token)


def _run(key, chips, ask_fn, max_seconds):
    ok, bad, started = set(), {}, time.time()
    try:
        for chip in chips:
            if time.time() - started > max_seconds:
                bad[chip] = "not checked (time limit)"
                continue
            good, why = check_one(ask_fn, chip)
            (ok.add(chip) if good else bad.__setitem__(chip, why))
    finally:
        with _lock:
            _cache[key] = {"at": time.time(), "ok": ok, "bad": bad, "partial": any("time limit" in v for v in bad.values())}
            _running.discard(key)
        worst = "; ".join(f"{k} ({v})" for k, v in list(sorted(bad.items()))[:6])
        print(f"[chip_health] {key}: {len(ok)} chips verified, {len(bad)} hidden" + (f" -> {worst}" if bad else ""))


def get_verified(key):
    """Set of chips verified for this key, or None when unknown/stale (verification not done yet)."""
    with _lock:
        c = _cache.get(key)
    if not c:
        return None
    ttl = _TTL_PARTIAL if c["partial"] else _TTL_OK
    return c["ok"] if time.time() - c["at"] < ttl else None


def ensure_verification(key, chips, ask_fn, max_seconds=180, background=True):
    """Starts one background check per key (never blocks the request, never runs twice at once)."""
    with _lock:
        if key in _running:
            return False
        _running.add(key)
    if background:
        threading.Thread(target=_run, args=(key, list(chips), ask_fn, max_seconds), daemon=True, name=f"chips-{key}").start()
    else:
        _run(key, list(chips), ask_fn, max_seconds)
    return True


def _ask_fn(role, institution_code, institution_type, db_name, db_server, db_user, db_password, hospital_name):
    def ask(chip):
        from agent.agent import ask_agent
        return ask_agent(question=chip, db_name=db_name, chat_history=[], is_premium=True, role=role, hospital_name=hospital_name,
                         db_server=db_server, db_user=db_user, db_password=db_password, institution_code=institution_code,
                         institution_type=institution_type)[0]
    return ask


def verified_chips(role, institution_code, institution_type, db_name, db_server, db_user, db_password, hospital_name):
    """What main.py calls: returns the verified set (or None while the first check is still running)."""
    key = f"{institution_code}:{role}"
    v = get_verified(key)
    if v is None:
        from agent.followups import all_chips
        ensure_verification(key, all_chips(institution_type),
                            _ask_fn(role, institution_code, institution_type, db_name, db_server, db_user, db_password, hospital_name))
    return v


def report():
    with _lock:
        return {k: {"checked_seconds_ago": int(time.time() - c["at"]), "ok": sorted(c["ok"]), "bad": dict(sorted(c["bad"].items()))} for k, c in _cache.items()}


def build_router(require_admin):
    from fastapi import APIRouter, Depends
    router = APIRouter()

    @router.get("/admin/chip-health")
    def chip_health(admin: str = Depends(require_admin)):
        return {"status": "success", "running": sorted(_running), "institutions": report()}

    return router
