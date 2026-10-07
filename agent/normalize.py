"""
Spelling-tolerant intent routing.

Why: the instant (zero-token) intents match on exact phrases, so "todays colection" or "top tests thsi
mnth" misses every intent and falls to the LLM — slower and it costs tokens. This repairs obvious typos
against the words our own intents already use. It is only tried when NO intent matched the question as
typed, so it can never change an answer that already worked, and the LLM still receives the user's
original wording.
"""
import difflib
import re

_WORD = re.compile(r"[a-z]+")

_BASE_WORDS = {
    "today", "yesterday", "tomorrow", "week", "month", "year", "quarter", "last", "this", "previous", "current",
    "january", "february", "march", "april", "june", "july", "august", "september", "october", "november", "december",
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
    "branch", "branches", "collection", "revenue", "patients", "patient", "tests", "packages", "doctors", "refunds",
    "pending", "summary", "dashboard", "total", "show", "list", "count", "bills", "bill", "recent", "latest", "growth",
}


def build_vocab(phrases) -> set:
    """Words (4+ letters) that our intents already understand."""
    vocab = set(_BASE_WORDS)
    for phrase in phrases:
        for w in _WORD.findall(str(phrase).lower()):
            if len(w) >= 4:
                vocab.add(w)
    return vocab


def _transposed(w: str, vocab: set):
    """'lsit' -> 'list': the word with two neighbouring letters swapped."""
    for i in range(len(w) - 1):
        cand = w[:i] + w[i + 1] + w[i] + w[i + 2:]
        if cand != w and cand in vocab:
            return cand
    return None


def correct_typos(q: str, vocab: set, cutoff: float = 0.84) -> str:
    """
    Replaces an unknown word with the closest known word (same first letter, similar length).
    5+ letter words: close match. 4-letter words (names like "Ravi", "Anil" live here): ONLY a swapped
    pair of letters or one missing/extra letter, so a person's name is never rewritten into a command.
    """
    def fix(m):
        w = m.group(0)
        if len(w) < 4 or w in vocab:
            return w
        fixed = _transposed(w, vocab)
        if fixed:
            return fixed
        pool = [v for v in vocab if v[0] == w[0] and abs(len(v) - len(w)) <= (1 if len(w) == 4 else 2)]
        best = difflib.get_close_matches(w, pool, n=1, cutoff=0.85 if len(w) == 4 else cutoff)
        return best[0] if best else w
    return _WORD.sub(fix, q or "")
