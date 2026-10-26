"""Reply in the user's language (English, Hindi, Telugu, Tamil, Kannada, Malayalam, Marathi, Bengali, Gujarati, Punjabi, Urdu, Odia).
The question is understood via agent.lang_bridge; the finished English answer is translated here. Numbers, names, IDs and
formatting are kept exactly. Uses the institution's own AI chain (never silently the shared one); on any problem the English answer is returned."""
import re
import threading

_SCRIPTS = [("hi", "Hindi", 0x0900, 0x097F), ("bn", "Bengali", 0x0980, 0x09FF), ("pa", "Punjabi", 0x0A00, 0x0A7F),
            ("gu", "Gujarati", 0x0A80, 0x0AFF), ("or", "Odia", 0x0B00, 0x0B7F), ("ta", "Tamil", 0x0B80, 0x0BFF),
            ("te", "Telugu", 0x0C00, 0x0C7F), ("kn", "Kannada", 0x0C80, 0x0CFF), ("ml", "Malayalam", 0x0D00, 0x0D7F),
            ("ur", "Urdu", 0x0600, 0x06FF)]
_MARATHI = re.compile(r"आहे|आहेत|किती|काय|मला|दाखवा|सांगा|माझ्या|झाले|झालेल")


def detect(text):
    """(code, language name) when the message is written in an Indian-language script; None for English / romanised text."""
    t = text or ""
    best, n = None, 0
    for code, name, lo, hi in _SCRIPTS:
        c = sum(1 for ch in t if lo <= ord(ch) <= hi)
        if c > n:
            best, n = (code, name), c
    if not best or n < 2:
        return None
    if best[0] == "hi" and _MARATHI.search(t):
        return ("mr", "Marathi")
    return best


_NAMES = {c: n for c, n, _, _ in _SCRIPTS}
_NAMES.update({"mr": "Marathi", "en": "English"})
_VOTES = {
    "te": "meeru miru emi enti ela evaru ekkada entha sevalu andistharu andhistharu andistaru cheppandi ivvandi chupinchandi kavali naaku naku maaku unnayi unnaru ledu nela enni ayyayi ayyindi ayindi chellinchanu chellimpulu baaki marchipoyanu naa mee mandhe ninna monna vaccharu vachindha vachindi mana manaku ippudu gata",
    "hi": "aapke aapka kya kitne kitna kitni mujhe batao bataiye dikhao dikhaiye kaise kahan nahin humein kaun kyun sabhi mahine mahina hue hua pichle pichla aaj kal",
    "ta": "neenga enna evlo irukku irukkum sollunga kaattunga engal ungal eppadi enga ennoda maadham kadantha ethanai",
    "kn": "nimma nanage yenu hege yaava beku torisi heli yeshtu illa tingalu kalede",
    "ml": "ningal engane aanu undo parayu kaanikku ethra entokke maasam kazhinja",
    "mr": "tumhi tumchya aahe aahet mala dakhva sanga kuthe kiti mahinyat jhale gelya",
    "bn": "apni apnar koto dekhan bolun amar kothay mashe hoyeche gato",
    "gu": "tame chhe batavo mane shu pachla thaya ketla",
    "pa": "tusi kithe dasso vekhao kinne bane",
    "or": "apana kemiti dekhantu kebe masa heichi",
}
_VOTES = {k: set(v.split()) for k, v in _VOTES.items()}
_WORD = re.compile(r"[a-z]+")


def _roman_lang(text):
    t = (text or "").lower()
    if not t.strip() or any(ord(c) > 127 for c in t):
        return None
    words = _WORD.findall(t)
    score = {k: sum(1 for w in words if w in v) for k, v in _VOTES.items()}
    best = max(score, key=score.get)
    return best if score[best] else None


def looks_roman(text):
    """cheap gate: English-letter text with words typical of Telugu/Hindi/Tamil/... (no AI call)."""
    if _roman_lang(text):
        return True
    try:
        from agent.lang_bridge import _MARK
        return bool(_MARK.search((text or "").lower()))
    except Exception:
        return False


def classify_roman(text, inst_code, timeout=15.0):
    """('te', 'Telugu', english_question) for Indian-language text typed in English letters; None for plain English / any problem.
    The language comes from the word votes (no AI); the AI only writes the English question, with the word-list translation as a fallback."""
    code = _roman_lang(text) or "te"
    hint = ""
    try:
        from agent.lang_bridge import to_english
        h, ch = to_english(text)
        hint = h if ch else ""
    except Exception:
        pass
    box = {}

    def work():
        try:
            from langchain_core.messages import SystemMessage, HumanMessage
            llm = _chain(inst_code)
            if llm is None:
                return
            sysm = ("Translate the user's message (an Indian language written in English letters) into ONE short plain English question for a "
                    "laboratory billing system. Keep every time-period word exactly (today, yesterday, this month, last month, last N months, last N days). "
                    "Never invent a period the user did not say. Keep names, bill numbers and numbers exactly. Output only the question.")
            msg = text + (("\n(word-list hint: " + hint + ")") if hint else "")
            r = llm.invoke([SystemMessage(content=sysm), HumanMessage(content=msg)])
            t = str(getattr(r, "content", r) or "").strip().strip('"').splitlines()[0].strip()
            if t:
                box["t"] = t
        except Exception:
            pass
    th = threading.Thread(target=work, daemon=True)
    th.start()
    th.join(timeout)
    en = box.get("t") or hint
    if not en or any(ord(c) > 127 for c in en):
        return None
    return (code, _NAMES[code], en)


def _chain(inst_code):
    from agent.agent import _data_chain
    ch = _data_chain(inst_code, True)
    return ch[0][1] if ch else None


def _translate(answer, lang_name, inst_code, timeout=40.0, roman=False):
    box = {}

    def work():
        try:
            from langchain_core.messages import SystemMessage, HumanMessage
            llm = _chain(inst_code)
            if llm is None:
                return
            how = (" written in English letters (Roman script, the way people type it in chat), not in native script" if roman else "")
            sysm = ("Translate the text to " + lang_name + how + ". Keep EXACTLY as written: all numbers, amounts, currency symbols, dates, bill numbers, IDs, "
                    "names of people, doctors, tests, organisations and branches, and all markdown (tables, bullets, bold, line breaks). "
                    "Translate every other word, including words such as patients, bills, tests, pending. Output only the translation, nothing else.")
            r = llm.invoke([SystemMessage(content=sysm), HumanMessage(content=answer)])
            t = str(getattr(r, "content", r) or "").strip()
            if t:
                box["t"] = t
        except Exception:
            pass
    th = threading.Thread(target=work, daemon=True)
    th.start()
    th.join(timeout)
    return box.get("t")


def localize(res, lang, inst_code):
    """res: the /ask or B2B chat response dict. Returns a copy with 'answer' translated (original kept in 'answer_en')."""
    if not lang or not isinstance(res, dict):
        return res
    ans = res.get("answer")
    if not isinstance(ans, str) or not ans.strip() or res.get("status") not in ("success", None):
        return res
    t = _translate(ans, lang[1], inst_code, roman=(len(lang) > 2 and lang[2] == "roman"))
    if not t:
        return res
    out = dict(res)
    out["answer_en"], out["answer"], out["lang"] = ans, t, lang[0]
    return out


def inst_from_activation(code):
    try:
        from auth.license_service import validate_license
        v = validate_license((code or "").strip()) or {}
        return v.get("institution_code") or v.get("db_name")
    except Exception:
        return None
