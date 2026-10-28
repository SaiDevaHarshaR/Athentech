"""Reply in the user's language (English, Hindi, Telugu, Tamil, Kannada, Malayalam, Marathi, Bengali, Gujarati, Punjabi, Urdu, Odia).
The question is understood via agent.lang_bridge; the finished English answer is translated here. Numbers, names, IDs and
formatting are kept exactly. Uses the institution's own AI chain (never silently the shared one); on any problem the English answer is returned."""
import re
import threading

_SCRIPTS = [("hi", "Hindi", 0x0900, 0x097F), ("bn", "Bengali", 0x0980, 0x09FF), ("pa", "Punjabi", 0x0A00, 0x0A7F),
            ("gu", "Gujarati", 0x0A80, 0x0AFF), ("or", "Odia", 0x0B00, 0x0B7F), ("ta", "Tamil", 0x0B80, 0x0BFF),
            ("te", "Telugu", 0x0C00, 0x0C7F), ("kn", "Kannada", 0x0C80, 0x0CFF), ("ml", "Malayalam", 0x0D00, 0x0D7F),
            ("ur", "Urdu", 0x0600, 0x06FF)]
_MARATHI = re.compile(r"(?<![\u0900-\u097f])(आहे|आहेत|किती|काय|मला|दाखवा|सांगा|माझ्या|माझी|माझे|झाले|झाली|झालेल\w*)(?![\u0900-\u097f])")


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
    "te": "meeru miru emi enti ela evaru ekkada entha sevalu andistharu andhistharu andistaru cheppandi ivvandi chupinchandi kavali naaku naku maaku unnayi unnaru ledu nela enni ayyayi ayyindi ayindi chellinchanu chellimpulu baaki marchipoyanu naa mee mandhe ninna monna vaccharu vachindha vachindi mana manaku ippudu gata meeru miru emi sevalu andhistharu andistharu istharu ekkuva ekkuvaga ayina parikshalu pariksha nundi vachayi oppandam oppandamu eppativaraku eppudu celluthundi chelluthundi gaduvu sadupayalu sadupayam daggara purti kaani inka kattali kattam kattamu kattu chivari chivarisari aakhari jarigindi motham mottam poyina pani chesina chese testulu packagelu entho istharu evi edi maa memu unnamu chupinchu",
    "hi": "aapke aapka kya kitne kitna kitni mujhe batao bataiye dikhao dikhaiye kaise kahan nahin humein kaun kyun sabhi mahine mahina hue hua pichle pichla aaj kal hain kab zyada sabse abhi bhugtan bakaya paisa rakam janchein sevayein suvidhayein suvidha dena kiya liya shakha beete beeta poori hui hamara hamari humne aakhri baar",
    "ta": "neenga enna evlo irukku irukkum sollunga kaattunga engal ungal eppadi enga ennoda maadham kadantha ethanai",
    "kn": "nimma nanna nanage yenu hege yaava beku torisi heli yeshtu eshtu ide aagide illa tingalu kalede namma bandideya bandide yavaga kone",
    "ml": "ningal engane aanu undo parayu kaanikku ethra entokke maasam kazhinja ente kudishika ethra thuka aake maasam maasathil",
    "mr": "tumhi tumchya aahe aahet mala dakhva sanga kuthe kiti mahinyat jhale gelya majhe majhi majha shevtache shevtacha kadhi amche amhi",
    "bn": "apni apnar koto dekhan bolun amar kothay mashe hoyeche gato apnara bolun koto amar mashe hoyeche bokeya poriman",
    "gu": "tame chhe batavo mane shu pachla thaya ketla ketlu ketli malyu amaru amari amaro maru mari hatu chhelu chhello thayu kyare chhu",
    "pa": "tusi kithe dasso vekhao kinne kinna kinni kinnian bane vich haige sanu tuhada pichle pichla mahine mahina",
    "or": "apana kemiti dekhantu kebe masa heichi kete mora mota rashi bakeya gata dena mo tume apana heichi",
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


_STRONG = {"kinna", "kinne", "kinni", "kinnian", "tusi", "tuhada", "dasso", "apnara", "bolun", "kudishika", "andhistharu", "niluvai", "thakbaki", "bokeya", "bakeya", "eshtu", "evlo", "ethra",
           "oppandam", "oppandamu", "eppativaraku", "sadupayalu", "chivarisari", "parikshalu", "kattali", "kattam", "celluthundi", "vachayi", "unnamu", "chesina", "chhe", "chhu", "ketlu", "ketla", "ketli", "malyu", "amaru", "amaro", "chhelu", "chhello", "aahe", "aahet", "majhe", "majhi", "shevtache", "shevtacha", "sanga", "kadhi", "kete", "kemiti", "bandideya", "bandide", "namma"}


def _foreign(t):
    """True when a translation contains letters of a script nobody asked for (Korean, Chinese, Japanese, Cyrillic): model glitch."""
    return bool(re.search("[\u0400-\u04ff\u3040-\u30ff\u4e00-\u9fff\uac00-\ud7af]", t or ""))


def _roman_votes(text):
    """(language, number of matching words, True if no other language ties)"""
    t = (text or "").lower()
    if not t.strip() or any(ord(c) > 127 for c in t):
        return None, 0, False
    words = _WORD.findall(t)
    score = {k: sum(1 for w in words if w in v) for k, v in _VOTES.items()}
    best = max(score, key=score.get)
    n = score[best]
    return (best if n else None), n, (n > 0 and sum(1 for v in score.values() if v == n) == 1)


def looks_roman(text):
    """cheap gate: English-letter text with words typical of Telugu/Hindi/Tamil/... (no AI call)."""
    if _roman_lang(text):
        return True
    try:
        from agent import kw_intent as _kw
        if _kw.kw_intent(text):
            return True
    except Exception:
        pass
    try:
        from agent.lang_bridge import _MARK
        return bool(_MARK.search((text or "").lower()))
    except Exception:
        return False



_LAST_W = {"gata", "gato", "gat", "gatha", "kalede", "kalada", "kazhinja", "kazhinju", "gelya", "gelela", "magchya", "pichle", "pichla", "pichhle", "kadantha", "pachla", "pachhla", "mugisida", "poyina", "beete", "beeta", "bita", "bite", "beeti"}
_THIS_W = {"ee", "ei", "ya", "aa", "indha", "is", "iss", "ye", "yah"}


def _fix_period(text, en):
    """The AI sometimes turns 'last month' into 'this month' (or the reverse) for English-letters questions: wrong data. Fix from the user's own words."""
    try:
        words = set(_WORD.findall((text or "").lower()))
        if re.search(r"\d", text or "") or not en:
            return en
        last, this = bool(words & _LAST_W), bool(words & _THIS_W)
        if last and not this and re.search(r"\bthis month\b", en, re.I):
            return re.sub(r"\bthis month\b", "last month", en, flags=re.I)
        if this and not last and re.search(r"\blast month\b", en, re.I):
            return re.sub(r"\blast month\b", "this month", en, flags=re.I)
    except Exception:
        pass
    return en


_THREE_W = re.compile(r"(?<![0-9])3(?![0-9])|\b(?:teen|tin|moodu|mudu|moonu|mooru|mundru|three|quarter)\b|\u0c69|\u0969|\u0bae\u0bc2\u0ba9\u0bcd\u0bb1\u0bc1|\u0cae\u0cc2\u0cb0\u0cc1|\u0d2e\u0d42\u0d28\u0d4d\u0d28\u0d4d|\u09a4\u09bf\u09a8|\u0aa4\u0acd\u0ab0\u0aa3|\u0a24\u0a3f\u0a70\u0a28|\u062a\u06cc\u0646|\u0b24\u0b3f\u0b28\u0b3f|\u0924\u0940\u0928|\u0c2e\u0c42\u0c21\u0c41|\u0c24\u0c4d\u0c30\u0c48|\u0924\u093f\u092e\u093e\u0939\u0940", re.I)


_BR_W = re.compile("branch|shakha|sakha|centre|\u0c2c\u0c4d\u0c30\u0c3e\u0c02\u0c1a\u0c4d|\u0c36\u0c3e\u0c16|\u092c\u094d\u0930\u093e\u0902\u091a|\u0936\u093e\u0916\u093e|\u0b95\u0bbf\u0bb3\u0bc8|\u0cb6\u0cbe\u0c96\u0cc6|\u0d36\u0d3e\u0d16|\u09b6\u09be\u0996\u09be|\u0ab6\u0abe\u0a96\u0abe|\u0a38\u0a3c\u0a3e\u0a16\u0a3e|\u0b36\u0b3e\u0b16\u0b3e", re.I)
_MOST_W = re.compile("ekkuva|ekkuvaga|zyada|jyada|adhik|sabse|busiest|busy|most|highest|\u0c0e\u0c15\u0c4d\u0c15\u0c41\u0c35|\u091c\u093c\u094d\u092f\u093e\u0926\u093e|\u091c\u094d\u092f\u093e\u0926\u093e|\u0905\u0927\u093f\u0915|\u0938\u092c\u0938\u0947|\u0935\u094d\u092f\u0938\u094d\u0924", re.I)


_LASTM_N = re.compile("\u0c17\u0c24 \u0c28\u0c46\u0c32|\u0c2a\u0c4b\u0c2f\u0c3f\u0c28 \u0c28\u0c46\u0c32|\u092a\u093f\u091b\u0932\u0947 \u092e\u0939\u0940\u0928\u0947|\u092c\u0940\u0924\u0947 \u092e\u0939\u0940\u0928\u0947|\u0b95\u0b9f\u0aa8\u0bcd\u0ba4 \u0bae\u0bbe\u0ba4\u0bae\u0bcd|\u0b95\u0b9f\u0ba8\u0bcd\u0ba4 \u0bae\u0bbe\u0ba4\u0bae\u0bcd|\u0c95\u0cb3\u0cc6\u0ca6 \u0ca4\u0cbf\u0c82\u0c97\u0cb3\u0cc1|\u0d15\u0d34\u0d3f\u0d1e\u0d4d\u0d1e \u0d2e\u0d3e\u0d38\u0d02|\u0917\u0947\u0932\u094d\u092f\u093e \u092e\u0939\u093f\u0928\u094d\u092f\u093e\u0924|\u0997\u09a4 \u09ae\u09be\u09b8\u09c7|\u0a97\u0aaf\u0abe \u0aae\u0ab9\u0abf\u0aa8\u0ac7|\u0a2a\u0a3f\u0a1b\u0a32\u0a47 \u0a2e\u0a39\u0a40\u0a28\u0a47|\u06af\u0632\u0634\u062a\u06c1 \u0645\u0627\u06c1|\u0b17\u0b24 \u0b2e\u0b3e\u0b38")
_PAYDUE_W = re.compile("(?:entha|evlo|eshtu|ethra|kitna|kitni|koto)\\s+(?:kattali|kattanu|kattalsi|katta|dena|deni|dhena|deva)|\u0c0e\u0c02\u0c24 \u0c15\u0c1f\u0c4d\u0c1f\u0c3e\u0c32\u0c3f|\u0915\u093f\u0924\u0928\u093e \u0926\u0947\u0928\u093e|\u0915\u093f\u0924\u0928\u093e \u092a\u0948\u0938\u093e \u0926\u0947\u0928\u093e", re.I)
_LASTPAY_W = re.compile("chivari|chivarisari|aakhri|aakhari|akhri|last|latest|\u0c1a\u0c3f\u0c35\u0c30\u0c3f|\u0906\u0916\u093f\u0930\u0940|\u0905\u0902\u0924\u093f\u092e", re.I)


_NOTDONE_W = re.compile("(?:poori|puri|pura|purti|purthi)\\s+(?:nahi|nahin|kaani|kaledu|avvaledu|agala)|\u092a\u0942\u0930\u0940 \u0928\u0939\u0940\u0902|\u0905\u0927\u0942\u0930\u0940|\u0c2a\u0c42\u0c30\u0c4d\u0c24\u0c3f \u0c15\u0c3e\u0c28\u0c3f|\u0c2a\u0c42\u0c30\u0c4d\u0c24\u0c3f \u0c15\u0c3e\u0c32\u0c47\u0c26\u0c41", re.I)


def _guard_3m(text, en):
    """'last month' must never turn into 'last 3 months' unless the user said three / 3 / quarter in their own words."""
    try:
        if en and re.search(r"(?i)\b(?:3|three)[\s-]+months?\b|\bquarter\b|\b90\s+days\b|\bthree-month", en) and not _THREE_W.search(text or "") and not re.search(r"(?i)\bcompare|comparison", en):
            if re.search(r"(?i)bill|invoice|billed|billing", en):
                return "How many bills did I get last month?"
            return re.sub(r"(?i)\b(?:the\s+)?(?:last|past|previous)\s+(?:3|three)\s+months\b", "last month", en)
    except Exception:
        pass
    return en


def classify_roman(text, inst_code, timeout=25.0):
    """('te', 'Telugu', english_question) for Indian-language text typed in English letters; None when it cannot be understood.
    The AI names the language and writes the English question; the word votes are the fallback."""
    votes = _roman_lang(text)
    try:        # known question recognised from its words: no AI call needed
        from agent import kw_intent as _kw
        _k = _kw.kw_intent(text)
        if _k:
            _v, _n, _u = _roman_votes(text)
            _c = (_v if (_v and _u) else None) or _kw.guess_lang(text) or votes or "hi"
            if _c not in _NAMES:
                _c = "hi"
            return (_c, _NAMES[_c], _k)
    except Exception as _e:
        print("[lang] kw roman: %s %s" % (type(_e).__name__, str(_e)[:100]), flush=True)
    r = to_english(text, inst_code, timeout, with_lang=True)
    if r:
        code, en = r
        v, n, unique = _roman_votes(text)
        if v and unique and (n >= 2 or any(w in _STRONG for w in _WORD.findall(text.lower()))):        # two or more clear words of one language beat the AI's guess
            code = v
        code = code or votes
        if not code:
            return None
        return (code, _NAMES[code], _fix_period(text, en))
    en = to_english(text, inst_code, timeout)        # same translation without the language code (language from the word votes)
    if not en:
        try:        # last fallback: word list (only when the AI could not answer in time)
            from agent.lang_bridge import to_english as _wl
            h, ch = _wl(text)
            en = h if ch else None
        except Exception:
            en = None
    if not en or any(ord(c) > 127 for c in en):
        return None
    code = votes or "hi"
    return (code, _NAMES[code], _fix_period(text, en))


def _bind_fast(llm):
    try:        # translation does not need long reasoning: much faster on gpt-oss models
        model = str(getattr(llm, "model_name", None) or getattr(llm, "model", "") or "").lower()
        if type(llm).__name__ == "ChatGroq" and "gpt-oss" in model:
            return llm.bind(reasoning_effort="low")
    except Exception:
        pass
    return llm


def _chain(inst_code):
    from agent.agent import _data_chain
    ch = _data_chain(inst_code, True)
    return _bind_fast(ch[0][1]) if ch else None


import threading as _th, time
_FLAG = _th.local()
_DEAD = set()
_COOL = {}


def _ask_ai(inst_code, messages, question=None, what="translate"):
    """Text of the first provider (the institution's own chain) that answers; None if all fail. Failures are logged, never raised."""
    try:
        from agent.agent import _data_chain
        chain = _data_chain(inst_code, True, question)
    except Exception as e:
        print("[lang] %s: no AI chain: %s %s" % (what, type(e).__name__, str(e)[:120]), flush=True)
        return None
    import os
    fb_models = [m.strip() for m in os.getenv("SAHASRA_LANG_FALLBACK_MODEL", "llama-3.3-70b-versatile,meta-llama/llama-4-scout-17b-16e-instruct,openai/gpt-oss-120b").split(",") if m.strip()]
    def _quick(m):
        for upd in ({"max_retries": 0, "request_timeout": 20}, {"max_retries": 0, "timeout": 20}, {"max_retries": 0}):
            try:
                return m.model_copy(update=upd)
            except Exception:
                continue
        return m

    for name, llm in (chain or []):
        tries = []
        if name == "groq" and fb_models:
            now = time.time()
            tries = [(m, lambda l=llm, m=m: _quick(l.bind(model=m))) for m in fb_models if (inst_code, m) not in _DEAD and _COOL.get((inst_code, m), 0) < now]
            tries.append(("main", lambda l=llm: _quick(_bind_fast(l))))
            if getattr(_FLAG, "main_first", False):
                tries.reverse()
        else:
            tries = [("main", lambda l=llm: _bind_fast(l))]
        for label, mk in tries:        # Groq: the small model first (own quota, fast, no internal 60 s retry loop), then the main one
            try:
                r = mk().invoke(messages)
                t = str(getattr(r, "content", r) or "").strip()
                if t:
                    return t
                print("[lang] %s: empty reply from %s/%s" % (what, name, label), flush=True)
            except Exception as e:
                print("[lang] %s: %s/%s failed: %s %s" % (what, name, label, type(e).__name__, str(e)[:100]), flush=True)
                es = str(e).lower()
                if label != "main":        # remember: a model this account cannot use is skipped for good, a rate-limited one for 60 s
                    if "404" in es or "does not exist" in es or "decommission" in es or "not found" in es:
                        _DEAD.add((inst_code, label))
                    elif "429" in es or "rate" in es:
                        _COOL[(inst_code, label)] = time.time() + 60
    return None


_CANON = ('How many bills did I get this month? | '
          'How many bills did I get last month? | '
          'What is my total billed amount in the last 3 months? | '
          'What is my outstanding balance? | '
          'What is my credit limit? | '
          'When was my last payment and how much? | '
          'Has our payment been received? | '
          'What services do you provide? | '
          'Which of my reports are pending? | '
          'What is the price of CBC? | '
          'How many invoices this month? | '
          'What is the status of my reports? | '
          'How much is pending against our account? | '
          'What is our available credit limit? | '
          'Can you provide the monthly billing statement? | '
          'Which tests are still pending? | '
          'Which orders are likely to be delayed? | '
          'What percentage of reports met TAT this month? | '
          'Which tests were ordered most frequently? | '
          'What is our sample rejection percentage? | '
          "Compare our last three months' invoices. | "
          'What is the price and report time for CBC? | '
          'What health-check packages are available? | '
          'Can you arrange sample pickup tomorrow? | '
          'Can I speak with the lab manager? | '
          'Download Excel | '
          'Talk to lab manager | '
          'Raise a delay complaint | '
          'Show rejected samples | '
          'Request invoice copy | '
          'Request GST invoice copy | '
          'Raise renewal request | '
          'Raise recollection request | '
          'Billing statement | '
          'Payment status | '
          'Outstanding balance | '
          'Status of my reports this month | '
          'Price of CBC | '
          'Raise a special rate request | '
          'Top 10 recent bills | '
          'Show health packages | '
          'Raise a support request | '
          'Billing total this month | '
          'When is the next payment due? | '
          'Which invoices are unpaid? | '
          'What is our outstanding balance and credit limit | '
          'Tests done this month | '
          'Contract agreement details | '
          'Which health packages are available | '
          'What is our pending balance? | '
          'Has our NEFT payment been received? | '
          'How much credit is available? | '
          'When does our agreement expire? | '
          'Has our credit note been approved? | '
          'Can we download our ledger? | '
          'Has our monthly invoice been generated? | '
          'What is our monthly billing total? | '
          'Which branch has the highest test volume? | '
          'How has our test volume changed this quarter? | '
          "Give me today's pending-order summary.")
_GLOSS = ("baaki, bakaya, thakbaki, niluvai, kudishika, bokeya, bakeya, బకాయి, बकाया = outstanding balance (money still to be paid, NOT pending tests); "
          "bill, billu = invoice/bill; payment, chellimpu, bhugtan, adaayi = payment made by the client; credit limit = credit limit; "
          "meeru/miru = you; emi/emi emi = what/which (Telugu question word, NOT an EMI instalment plan); andhistharu/andistharu/istharu = provide/offer; undi = is there; "
          "tingalu/tingala/tingalalli = month(s); ottu/mottha/mottam/motham = total; ee/ei/ya/aa/indha = this; "
          "sevalu, sevaigal, seve, services = services; nela, mahina, maadham, tingalu, maasam, mashe, masa = month; gata, gato, pichle, pichla, kadantha, kalede, kazhinja, gelya, gelela, pachla = last/previous (NOT this); "
          "oppandam, oppandamu = contract agreement; eppativaraku, eppativarku = until when; gaduvu = deadline/expiry; sadupayalu, sadupayam = facilities = services; purti kaani, inka purtikaledu = not completed = pending; "
          "parikshalu, pariksha = tests; chivarisari, chivari sari = last time; kattam, kattamu, kattali, kattu = pay/paid; ekkuva, ekkuvaga = most; order ayina = ordered; nundi = from; vachayi = came; pani chesina = handled; shakha, sakha = branch; "
          "sabse zyada = most; kul, motham, mottam = total (NEVER write 3 months unless the user says three/3/quarter: a plain last month is last month); beete, bita = last; "
          "contract, agreement, ఒప్పందం, एग्रीमेंट, कॉन्ट्रैक्ट, करार = contract agreement; ledger, లెడ్జర్, लेज़र = ledger; TDS = tax deducted at source; credit note = credit note; "
          "package, ప్యాకేజీ, पैकेज = health-check package (list them, do NOT answer with services); parikshalu, janchen, jaanch = tests; ఆలస్యం, देरी, delay + complaint/ఫిర్యాదు/शिकायत = Raise a delay complaint; "
          "lab manager, ల్యాబ్ మేనేజర్, लैब मैनेजर + talk/speak/మాట్లాడ/बात = Can I speak with the lab manager?; special rate, ప్రత్యేక రేటు, विशेष दर = Raise a special rate request; renewal, రెన్యువల్, नवीनीकरण = Raise renewal request; "
          "recollection, రీకలెక్షన్, पुनः संग्रह = Raise recollection request; excel, ఎక్సెల్, एक्सेल + download = Download Excel; tests done / చేసిన పరీక్షలు / की गई जाँचें = Tests done this month; "
          "most ordered / ఎక్కువగా ఆర్డర్ / सबसे ज़्यादा मँगाई = Which tests were ordered most frequently?; branch + highest/most = Which branch has the highest test volume?; quarter, త్రైమాసిక, तिमाही + volume = How has our test volume changed this quarter?; "
          "percentage/శాతం/प्रतिशत + TAT = What percentage of reports met TAT this month?")
_QCACHE = {}


_QCACHE2 = {}
_LANGCODES = ("te", "hi", "ta", "kn", "ml", "mr", "bn", "gu", "pa", "ur", "or")


def to_english(text, inst_code, timeout=25.0, with_lang=False):
    """One short AI call: the question in any supported language -> a plain English question the chat already understands.
    with_lang=True returns (language code, English question) instead. None on any problem."""
    t = (text or "").strip()
    if not t:
        return None
    cache = _QCACHE2 if with_lang else _QCACHE
    if t in cache:
        return cache[t]
    box = {}

    def work():
        try:
            from langchain_core.messages import SystemMessage, HumanMessage
            sysm = ("Rewrite the user's message (any Indian language, in native script or English letters) as ONE short plain English question for a "
                    "laboratory's corporate-client portal: bills, billed amount, payments received, outstanding balance, credit limit, test prices, "
                    "report status, sample tracking, contract/agreement, health packages, tests ordered, branches, TAT, sample rejection, ledger/statements, support requests (delay complaint, special rate, renewal, recollection, lab manager, sample pickup, invoice copy, Excel download). Keep every time-period word exactly (today, yesterday, this month, last month, last N months, last N days) and "
                    "never invent a period the user did not say. If the meaning matches one of these questions, output THAT question word for word, unchanged: " + _CANON + ". "
                    "Glossary: " + _GLOSS + ". Keep names, bill numbers and numbers exactly. ")
            if with_lang:
                sysm += ("Reply in this exact format: <code>|<English question> where <code> is the language of the user's message: "
                         "te Telugu, hi Hindi, ta Tamil, kn Kannada, ml Malayalam, mr Marathi, bn Bengali, gu Gujarati, pa Punjabi, ur Urdu, or Odia. Nothing else.")
            else:
                sysm += "Output only the English question."
            txt = _ask_ai(inst_code, [SystemMessage(content=sysm), HumanMessage(content=t)], None, "question")
            line = (txt or "").strip().strip('"').splitlines()[0].strip() if txt else ""
            if with_lang:
                line = re.sub(r"</?code>", "|", line)
                line = re.sub(r"<([A-Za-z]{2})>", r"\1|", line)
                _nm = {v.lower(): k for k, v in _NAMES.items()}
                _mn = re.match(r"^\W*([A-Za-z]{4,9})\W{0,3}[|:\u2013-]\s*(.+)$", line)
                if _mn and _mn.group(1).lower() in _nm:
                    line = _nm[_mn.group(1).lower()] + "|" + _mn.group(2)
                m = re.match(r"^\W*([A-Za-z]{2})\W{0,3}[|:\u2013-]\s*(.+)$", line)
                if m and len(m.group(2)) <= 300:
                    c = m.group(1).lower()
                    box["q"] = (c if c in _LANGCODES else None, m.group(2).strip().strip('"'))
                else:
                    print("[lang] question: unparsed reply: %s" % line[:100], flush=True)
            elif line and len(line) <= 300:
                box["q"] = line
        except Exception as e:
            print("[lang] question: %s %s" % (type(e).__name__, str(e)[:120]), flush=True)
    th = threading.Thread(target=work, daemon=True)
    th.start()
    th.join(timeout)
    q = box.get("q")
    eng = q[1] if with_lang and q else q
    _h = _hint_fix(t, eng)
    if _h and _h != eng:
        print("[lang] question: intent fixed from the user's words", flush=True)
        eng = _h
        q = (q[0] if (with_lang and q) else None, eng) if with_lang else eng
    if eng:
        eng = eng.replace("\u2019", "'").replace("\u2018", "'").replace("\u201c", '"').replace("\u201d", '"').replace("\u2013", "-").replace("\u2011", "-").replace("\u2014", "-").replace("\u20b9", "Rs ")
        q = (q[0], eng) if with_lang else eng
    try:
        try:
            from agent import kw_intent as _kw
        except Exception:
            import kw_intent as _kw
        _k = _kw.kw_intent(t)
        if _k and _k != eng:
            print("[lang] question: fixed from the user's words -> %s" % _k, flush=True)
            eng = _k
            q = (q[0] if (with_lang and q) else None, eng) if with_lang else eng
    except Exception as _e:
        print("[lang] kw: %s %s" % (type(_e).__name__, str(_e)[:100]), flush=True)
    if eng and _BR_W.search(t) and _MOST_W.search(t) and not re.search(r"(?i)branch", eng):
        eng = "Which branch has the highest test volume?"
        print("[lang] question: branch question fixed from the user's words", flush=True)
    if eng and _PAYDUE_W.search(t) and not _LASTPAY_W.search(t) and not re.search(r"(?i)outstanding|balance|due", eng):
        eng = "What is my outstanding balance?"
        print("[lang] question: how much to pay -> outstanding balance", flush=True)
    if eng and _NOTDONE_W.search(t) and not re.search(r"(?i)pending|not completed", eng):
        eng = "Which tests are still pending?"
        print("[lang] question: not completed -> pending tests", flush=True)
    if eng and _LASTM_N.search(t) and not _THREE_W.search(t) and not re.search(r"(?i)last month|previous month", eng):
        if re.search(r"(?i)bill|invoice|billed|billing", eng):
            eng = "How many bills did I get last month?"
        else:
            eng = re.sub(r"(?i)\bthis month\b", "last month", eng)
        print("[lang] question: last month kept (not this month / 3 months)", flush=True)
    if eng:
        _g = _guard_3m(t, eng)
        if _g != eng:
            print("[lang] question: period fixed (last month, not 3 months)", flush=True)
            eng = _g
    if eng:
        try:
            _m = re.match(r"(?i)^\s*(?:is|are|do you (?:have|do|offer|provide)) (?:the |a )?([a-z0-9][a-z0-9 \-]{2,40}?)(?: test)? (?:available|offered|done|there)\s*\??\s*$", eng)
            if _m and not re.search(r"(?i)packag|service|credit|report|excel|statement|ledger|invoice|bill|branch|payment|sample|pickup|manager", _m.group(1)):
                eng = "What is the price of %s?" % _m.group(1).strip()
                print("[lang] question: availability asked -> price lookup", flush=True)
            try:
                from agent import intent_match as _im
            except Exception:
                import intent_match as _im
            try:
                from auth.b2b_gate import is_exact as _ie
                _exact = bool(_ie(eng))
            except Exception:
                _exact = False
            if not _exact:
                _c, _sc = _im.canonical(eng)
                if _c and _c != eng:
                    print("[lang] question: matched a known question (%.2f)" % _sc, flush=True)
                    eng = _c
                elif not _c:
                    _im.log_unmatched(t, eng)
            q = (q[0] if (with_lang and q) else None, eng) if with_lang else eng
        except Exception as _e:
            print("[lang] match: %s %s" % (type(_e).__name__, str(_e)[:100]), flush=True)
    if eng and not any(ord(c) > 127 for c in eng):
        if len(cache) > 500:
            cache.clear()
        cache[t] = q
        return q
    return None


def _in_script(text, code):
    lo_hi = {c: (lo, hi) for c, _, lo, hi in _SCRIPTS}
    lo_hi["mr"] = lo_hi["hi"]
    if code not in lo_hi:
        return False
    lo, hi = lo_hi[code]
    letters = [ch for ch in (text or "") if ch.isalpha()]
    return bool(letters) and sum(1 for ch in letters if lo <= ord(ch) <= hi) / len(letters) > 0.5


_TERM_KEYS = ["outstanding balance", "billed amount", "payments received", "credit limit", "bills", "tests", "packages", "report status", "sample tracking", "pending", "last month", "not cash"]
_TERMS = {
    "te": "బకాయి మొత్తం|బిల్ చేసిన మొత్తం|అందిన చెల్లింపులు|క్రెడిట్ పరిమితి|బిల్లులు|పరీక్షలు|ప్యాకేజీలు|రిపోర్ట్ స్థితి|శాంపిల్ ట్రాకింగ్|పెండింగ్|గత నెల|నగదు కాదు",
    "hi": "बकाया राशि|बिल की गई राशि|प्राप्त भुगतान|क्रेडिट सीमा|बिल|जाँच|पैकेज|रिपोर्ट की स्थिति|सैंपल ट्रैकिंग|लंबित|पिछला महीना|नकद नहीं",
    "ta": "நிலுவைத் தொகை|பில் செய்த தொகை|பெறப்பட்ட பணம்|கிரெடிட் வரம்பு|பில்கள்|பரிசோதனைகள்|பேக்கேஜ்கள்|அறிக்கை நிலை|மாதிரி கண்காணிப்பு|நிலுவையில்|கடந்த மாதம்|பணம் அல்ல",
    "kn": "ಬಾಕಿ ಮೊತ್ತ|ಬಿಲ್ ಮಾಡಿದ ಮೊತ್ತ|ಸ್ವೀಕರಿಸಿದ ಪಾವತಿಗಳು|ಕ್ರೆಡಿಟ್ ಮಿತಿ|ಬಿಲ್‌ಗಳು|ಪರೀಕ್ಷೆಗಳು|ಪ್ಯಾಕೇಜ್‌ಗಳು|ವರದಿ ಸ್ಥಿತಿ|ಮಾದರಿ ಟ್ರ್ಯಾಕಿಂಗ್|ಬಾಕಿ|ಕಳೆದ ತಿಂಗಳು|ನಗದು ಅಲ್ಲ",
    "ml": "കുടിശ്ശിക തുക|ബിൽ ചെയ്ത തുക|ലഭിച്ച പേയ്‌മെന്റുകൾ|ക്രെഡിറ്റ് പരിധി|ബില്ലുകൾ|പരിശോധനകൾ|പാക്കേജുകൾ|റിപ്പോർട്ട് നില|സാമ്പിൾ ട്രാക്കിംഗ്|തീർപ്പാക്കാത്തത്|കഴിഞ്ഞ മാസം|പണമല്ല",
    "mr": "थकबाकी|बिल केलेली रक्कम|प्राप्त पेमेंट|क्रेडिट मर्यादा|बिले|चाचण्या|पॅकेजेस|अहवालाची स्थिती|नमुना ट्रॅकिंग|प्रलंबित|मागील महिना|रोख नाही",
    "bn": "বকেয়া|বিল করা পরিমাণ|প্রাপ্ত পেমেন্ট|ক্রেডিট সীমা|বিল|পরীক্ষা|প্যাকেজ|রিপোর্টের অবস্থা|নমুনা ট্র্যাকিং|মুলতুবি|গত মাস|নগদ নয়",
    "gu": "બાકી રકમ|બિલ કરેલી રકમ|મળેલ ચુકવણીઓ|ક્રેડિટ મર્યાદા|બિલ|ટેસ્ટ|પેકેજ|રિપોર્ટની સ્થિતિ|સેમ્પલ ટ્રેકિંગ|બાકી|છેલ્લો મહિનો|રોકડ નહીં",
    "pa": "ਬਕਾਇਆ ਰਕਮ|ਬਿੱਲ ਕੀਤੀ ਰਕਮ|ਪ੍ਰਾਪਤ ਅਦਾਇਗੀਆਂ|ਕ੍ਰੈਡਿਟ ਸੀਮਾ|ਬਿੱਲ|ਟੈਸਟ|ਪੈਕੇਜ|ਰਿਪੋਰਟ ਦੀ ਸਥਿਤੀ|ਸੈਂਪਲ ਟ੍ਰੈਕਿੰਗ|ਬਕਾਇਆ|ਪਿਛਲਾ ਮਹੀਨਾ|ਨਕਦ ਨਹੀਂ",
    "ur": "بقایا رقم|بل کی گئی رقم|موصول ادائیگیاں|کریڈٹ حد|بل|ٹیسٹ|پیکیج|رپورٹ کی حالت|سیمپل ٹریکنگ|زیر التوا|پچھلا مہینہ|نقد نہیں",
    "or": "ବକେୟା ରାଶି|ବିଲ୍ ହୋଇଥିବା ରାଶି|ପ୍ରାପ୍ତ ପେମେଣ୍ଟ|କ୍ରେଡିଟ୍ ସୀମା|ବିଲ୍|ପରୀକ୍ଷା|ପ୍ୟାକେଜ୍|ରିପୋର୍ଟ ସ୍ଥିତି|ନମୁନା ଟ୍ରାକିଂ|ବକେୟା|ଗତ ମାସ|ନଗଦ ନୁହେଁ",
}


def _term_line(code):
    v = _TERMS.get(code or "")
    if not v:
        return ""
    return " Use exactly these words: " + "; ".join("%s = %s" % (k, w) for k, w in zip(_TERM_KEYS, v.split("|"))) + "."


def _nums(text):
    import unicodedata
    t = "".join(str(unicodedata.digit(c)) if c.isdigit() and not c.isascii() else c for c in (text or ""))
    t = re.sub(r"(?<=\d),(?=\d)", "", t)
    return set(re.findall(r"\d+(?:\.\d+)?", t))


def _translate(answer, lang_name, inst_code, timeout=60.0, roman=False, code=None, strict=False):
    box = {}

    def work():
        try:
            from langchain_core.messages import SystemMessage, HumanMessage
            how = (" written in English letters (Roman script, the way people type it in chat), not in native script" if roman else "")
            sysm = ("Translate the text to " + lang_name + how + ". Keep EXACTLY as written: all numbers, amounts, currency symbols, dates, bill numbers, IDs, "
                    "names of people, doctors, tests, organisations and branches, and all markdown (tables, bullets, bold, line breaks). "
                    "Translate every other word, including words such as patients, bills, tests, pending. Never drop, merge or round a number: every number and amount in the text must appear in the translation. "
                    "Do not transliterate English words into the target script when a proper word exists (for example write the local word for bill, outstanding, billed)." + (" Write EVERYTHING in English letters only, never in native script." if roman else "") + ("" if roman else _term_line(code))
                    + (" IMPORTANT: your previous translation lost a number. Keep EVERY number and amount, and keep the whole message." if strict else "")
                    + " Output only the translation, nothing else.")
            t = _ask_ai(inst_code, [SystemMessage(content=sysm), HumanMessage(content=answer)], None, "answer")
            if t:
                box["t"] = t
        except Exception as e:
            print("[lang] answer: %s %s" % (type(e).__name__, str(e)[:120]), flush=True)
    th = threading.Thread(target=work, daemon=True)
    th.start()
    th.join(timeout)
    return box.get("t")



# ---- translation memory: the English answer with its numbers cut out is translated ONCE (best model, fully checked) and kept -----------------
# Later answers reuse it instantly: the numbers are put back by code, so they can never be altered, and the wording is the same every time.
_NUMTOK = re.compile(r"(?<![\w.])(?:\d{4}-\d{2}-\d{2}|₹?\d+(?:,\d+)*(?:\.\d+)?)(?![\w])")
_MON = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


def _iso_dates(t):
    """'24 Oct 2026' / '16 October 2026' / 2026<U+2011>10<U+2011>24 -> 2026-10-24 (one slot, same in every language)."""
    t = re.sub(r"(\d{4})[\u2010\u2011\u2012\u2013](\d{2})[\u2010\u2011\u2012\u2013](\d{2})", r"\1-\2-\3", t)

    def f(m):
        mo = _MON.get(m.group(2)[:3].lower())
        return "%s-%02d-%02d" % (m.group(3), mo, int(m.group(1))) if mo else m.group(0)
    return re.sub(r"\b(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?,?\s+(\d{4})\b", f, t)


# fixes for wording errors found by reading the saved translations (applied once, before a translation is saved)
_PAYW = re.compile("payment|chellimpu|bhugtan|bhugtaan|adaigi|adayegi|chukvani|chukvan|pavati|paavti|చెల్లింపు|भुगतान|पेमेंट|பேமெண்ட்|பணம் செலுத்|செலுத்த|கட்டண|பணம்|ಪಾವತಿ|പേയ്‌?മെന്റ്|പണമടയ്|পেমেন্ট|পরিশোধ|પેમેન્ટ|ચુકવણી|ਅਦਾਇਗੀ|ਭੁਗਤਾਨ|ਪੇਮੈਂਟ|ادائیگی|پیمنٹ|ପେମେଣ୍ଟ|ଦେୟ", re.I)
_LASTW = re.compile("chivari|akhri|aakhri|akhiri|antim|kadaisi|kone|avasana|shevt|shesh|sesh|chhell|chhel|\\blast\\b|\\blatest\\b|ఆఖరి|చివరి|आखिरी|आख़िरी|अंतिम|கடைசி|ಕೊನೆಯ|അവസാന|शेवटच|শেষ|છેલ્લ|ਆਖਰੀ|ਆਖ਼ਰੀ|آخری|ଶେଷ", re.I)
_RECVW = re.compile("vachindha|vachinda|andinda|mil gaya|mil gayi|mila|mili|kidaith|kidaichu|bandide|bandideya|kittiyo|kitti|milale|milala|peyechen|peyecho|malyu|mali\\b|milila|milichi|అందిం|వచ్చింద|మిల|मिल गया|मिल गई|मिला|मिळाल|प्राप्त|கிடைத்|பெறப்பட்ட|ಬಂದಿ|ಸ್ವೀಕರ|കിട്ടി|ലഭിച്ച|পাওয়া গেছে|পেয়ে|મળ્યું|મળી|ਮਿਲ|موصول|مل گی|مل گئ|مل گیا|ମିଳିଲା|ମିଳିଛି|ପାଇଛ", re.I)
_OUTW = re.compile("outstanding|bakaya|bakaayi|baaki|baki\\b|thakbaki|niluvai|kudishika|bokeya|bakeya|బకాయి|बकाया|நிலுவை|ಬಾಕಿ|കുടിശ്ശിക|കുടിശിക|थकबाकी|बाकी|বকেয়া|બાકી|ਬਕਾਇਆ|بقایا|ବକେୟା", re.I)
_MONTHW = re.compile("mahin|nela|maas|masa|maadha|tingal|mashe|\\bmonth|महीन|महिन|माह|నెల|மாத|ತಿಂಗಳ|മാസ|মাস|માસ|મહિન|ਮਹੀਨ|مہین|ମାସ", re.I)
_CANON_LAST = "When was my last payment and how much?"
_CANON_RECV = "Has our payment been received?"
_CANON_OUT = "What is my outstanding balance?"
_CANON_CREDIT = "What is my credit limit?"
_CANON_THIS = "How many bills did I get this month?"
_CANON_LASTM = "How many bills did I get last month?"
_CREDW = re.compile("credit|क्रेडिट|క్రెడిట్|கிரெடிட்|ಕ್ರೆಡಿಟ್|ക്രെഡിറ്റ്|ক্রেডিট|ક્રેડિટ|ਕ੍ਰੈਡਿਟ|کریڈٹ|କ୍ରେଡିଟ୍", re.I)
_LIMW = re.compile("limit|లిమిట్|लिमिट|सीमा|मर्यादा|పరిమితి|వరం|வரம்பு|லிமிட்|ಮಿತಿ|ಲಿಮಿಟ್|പരിധി|ലിമിറ്റ്|সীমা|লিমিট|મર્યાદા|લિમિટ|ਸੀਮਾ|ਲਿਮਿਟ|لمٹ|حد|ସୀମା|ଲିମିଟ୍|maryada|seema|parimiti|ellai|mithi|paridhi", re.I)
_BILLW = re.compile("bill|invoice|बिल|బిల్|பில்|ಬಿಲ್|ബിൽ|ബില്ല|বিল|બિલ|ਬਿੱਲ|ବିଲ୍", re.I)
_LASTM_T = {"gata", "gato", "gat", "gatha", "kalede", "kalada", "kazhinja", "kazhinju", "gelya", "gelela", "magchya", "pichle", "pichla", "pichhle", "kadantha", "pachla", "pachhla", "mugisida", "poyina", "last", "previous", "past",
            "గత", "पिछले", "पिछला", "गेल्या", "मागील", "கடந்த", "ಕಳೆದ", "കഴിഞ്ഞ", "গত", "છેલ્લા", "ગયા", "ਪਿਛਲੇ", "پچھلے", "ଗତ"}
_THISM_T = {"ee", "ei", "ya", "aa", "indha", "is", "iss", "ye", "yah", "ihi", "this", "ఈ", "इस", "या", "இந்த", "ಈ", "ഈ", "এই", "આ", "ਇਸ", "اس", "ଏହି", "हा"}
_URDU_BILL = {"بل", "بلز", "بلوں"}


def _toks(t):
    return set(re.findall(r"[^\s\?\.,!:;।\"'()\-]+", (t or "").lower()))


def _hint(text):
    """(canonical English question, strong) from the user's own words, no AI. strong = always use it (payment / outstanding / credit limit / last N months);
    weak = only when the AI could not answer (bills this / last month). None when unsure."""
    t = text or ""
    tk = _toks(t)
    if len(tk) > 12 or re.search(r"\d{3,}|[A-Za-z]+\d", t):        # long / compound question, bill number or code: leave it to the AI
        return None
    pay, out = bool(_PAYW.search(t)), bool(_OUTW.search(t))
    cred = bool(_CREDW.search(t))
    mon = bool(_MONTHW.search(t))
    bill = bool(_BILLW.search(t)) or bool(tk & _URDU_BILL)
    m = re.search(r"(?<!\d)(\d{1,2})(?!\d)", t)
    if m:
        n = int(m.group(1))
        if 2 <= n <= 12 and mon and (tk & _LASTM_T) and bill and not pay and not out and not cred:
            return ("What is my total billed amount in the last %d months?" % n, True)
        return None
    if mon:
        if pay or out or cred or not bill:
            return None
        if len(tk) > 8:
            return None
        if tk & _LASTM_T:
            return (_CANON_LASTM, False)
        if tk & _THISM_T:
            return (_CANON_THIS, False)
        return None
    if out and cred:
        return None
    if cred and _LIMW.search(t) and not pay:
        return (_CANON_CREDIT, True)
    if pay and _LASTW.search(t):
        return (_CANON_LAST, True)
    if pay and _RECVW.search(t):
        return (_CANON_RECV, True)
    if out and not pay:
        return (_CANON_OUT, True)
    return None


def _hint_fix(text, eng):
    """The AI sometimes turns 'my last payment' into a bills question, asks for a bill number, or answers a different period: for these fixed questions use the exact English wording
    (it then goes to the fixed, verified answer in every language). The weak ones (bills this / last month) are used only when the AI gave nothing."""
    try:
        h = _hint(text)
        if not h:
            return eng
        canon, strong = h
        if strong or not eng:
            return canon
    except Exception:
        pass
    return eng


_FIXES = {
    "ur": [("پہلی لیجر اندراج", "آخری لیجر اندراج"), ("جیسے کہ ", "")],
    "hi": [("आपका बिल की गई", "आपकी बिल की गई"), ("जैसे कि अंतिम", "अंतिम")],
    "kn": [("ನಿರ್ಣಾಯಕ ಸೇವೆ", "ರೋಗನಿರ್ಣಯ ಸೇವೆ")],
    "ta": [("அந்தப் பணிக்குப் பிறகு", "அந்தக் கட்டணத்திற்குப் பிறகு")],
    "ml": [("അത്‌ക്കു ശേഷം", "ആ പേയ്‌മെന്റിനു ശേഷം"), ("തുടര്ന്നു", "തുടർന്നു")],
    "te": [("నిర్ధారణ సేవల", "రోగనిర్ధారణ సేవల")],
}
_TM_MEM = {}


def _tm_db():
    import os, sqlite3
    p = os.getenv("SAHASRA_LANG_TM_DB") or os.path.join(os.getcwd(), "lang_tm.db")
    c = sqlite3.connect(p, timeout=5)
    c.execute("CREATE TABLE IF NOT EXISTS tm (lang TEXT, roman INTEGER, src TEXT, out TEXT, created TEXT DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY (lang, roman, src))")
    return c


def _tm_get(lang, roman, src):
    k = (lang, int(roman), src)
    if k in _TM_MEM:
        return _TM_MEM[k]
    try:
        c = _tm_db()
        try:
            r = c.execute("SELECT out FROM tm WHERE lang=? AND roman=? AND src=?", (lang, int(roman), src)).fetchone()
        finally:
            c.close()
        if r:
            _TM_MEM[k] = r[0]
            return r[0]
    except Exception as e:
        print("[lang] tm read: %s %s" % (type(e).__name__, str(e)[:80]), flush=True)
    return None


def _tm_put(lang, roman, src, out):
    _TM_MEM[(lang, int(roman), src)] = out
    try:
        c = _tm_db()
        try:
            c.execute("INSERT OR REPLACE INTO tm (lang, roman, src, out) VALUES (?,?,?,?)", (lang, int(roman), src, out))
            c.commit()
        finally:
            c.close()
    except Exception as e:
        print("[lang] tm write: %s %s" % (type(e).__name__, str(e)[:80]), flush=True)


def _leaks(out, src):
    """English words left inside a native-script translation (brand names written in capitals are allowed)."""
    allowed = set(w.upper() for w in re.findall(r"[A-Za-z]{2,}", " ".join(re.findall(r"\b[A-Z][A-Z0-9\-]{3,}\b", src or ""))))
    return [w for w in re.findall(r"[A-Za-z]{4,}", out or "") if w.upper() not in allowed]


def _tm_translate(ans, lang_name, inst_code, roman, code):
    """Translated answer using the memory (or None: caller uses the normal path)."""
    nums = []
    ans = _iso_dates(ans)

    def rep(m):
        nums.append(m.group(0))
        return "{N%d}" % len(nums)
    tpl = _NUMTOK.sub(rep, ans)
    if len(nums) > 12 or len(tpl) > 700 or "|" in tpl and len(tpl) > 400:
        return None
    out = _tm_get(code, roman, tpl)
    if out is None:
        try:
            _FLAG.main_first = True        # one-off, then reused for ever: spend the best model on it
            cand = _translate(tpl, lang_name, inst_code, roman=roman, code=code, strict=True)
        finally:
            _FLAG.main_first = False
        want = sorted(re.findall(r"\{N\d+\}", tpl))
        ok = bool(cand) and sorted(re.findall(r"\{N\d+\}", cand)) == want and not _foreign(cand) and (roman or len(_leaks(cand, tpl)) < 1)
        if not ok:
            print("[lang] tm: translation rejected (placeholders/glitch/English left), normal path", flush=True)
            return None
        out = cand.strip()
        if "\n" not in tpl:
            out = re.sub(r"\s*\n\s*", " ", out)        # the model split one sentence over two lines
        for a, b in _FIXES.get(code, []):
            out = out.replace(a, b)
        _tm_put(code, roman, tpl, out)
    for i, n in enumerate(nums, 1):
        out = out.replace("{N%d}" % i, n)
    return out


_LBL_EN = ["Credit terms", "Recent payments", "Item", "Value", "Date", "Paid", "Mode", "Balance after", "Concession", "Credit account", "Credit limit", "Credit period",
           "Grace period (days)", "Current outstanding", "Available credit", "Yes", "No", "Month", "Bill", "Patient", "Tests", "Billed amount", "Reports ready", "Amount"]
_LBL = {
 "te": "క్రెడిట్ నిబంధనలు|ఇటీవలి చెల్లింపులు|అంశం|విలువ|తేదీ|చెల్లించినది|విధానం|తర్వాత బ్యాలెన్స్|రాయితీ|క్రెడిట్ ఖాతా|క్రెడిట్ పరిమితి|క్రెడిట్ వ్యవధి|గ్రేస్ పీరియడ్ (రోజులు)|ప్రస్తుత బకాయి|అందుబాటులో ఉన్న క్రెడిట్|అవును|కాదు|నెల|బిల్|రోగి|పరీక్షలు|బిల్ చేసిన మొత్తం|సిద్ధమైన రిపోర్టులు|మొత్తం",
 "hi": "क्रेडिट शर्तें|हाल के भुगतान|विवरण|मान|तारीख|भुगतान|माध्यम|भुगतान के बाद शेष|रियायत|क्रेडिट खाता|क्रेडिट सीमा|क्रेडिट अवधि|ग्रेस अवधि (दिन)|वर्तमान बकाया|उपलब्ध क्रेडिट|हाँ|नहीं|महीना|बिल|मरीज़|जाँचें|बिल की गई राशि|तैयार रिपोर्ट|राशि",
 "ta": "கிரெடிட் விதிமுறைகள்|சமீபத்திய பேமெண்ட்கள்|விவரம்|மதிப்பு|தேதி|செலுத்தியது|முறை|பிறகு நிலுவை|தள்ளுபடி|கிரெடிட் கணக்கு|கிரெடிட் வரம்பு|கிரெடிட் காலம்|கருணைக் காலம் (நாட்கள்)|தற்போதைய நிலுவை|கிடைக்கும் கிரெடிட்|ஆம்|இல்லை|மாதம்|பில்|நோயாளி|பரிசோதனைகள்|பில் செய்த தொகை|தயாரான அறிக்கைகள்|தொகை",
 "kn": "ಕ್ರೆಡಿಟ್ ನಿಯಮಗಳು|ಇತ್ತೀಚಿನ ಪಾವತಿಗಳು|ವಿವರ|ಮೌಲ್ಯ|ದಿನಾಂಕ|ಪಾವತಿಸಿದ್ದು|ವಿಧಾನ|ನಂತರದ ಬಾಕಿ|ರಿಯಾಯಿತಿ|ಕ್ರೆಡಿಟ್ ಖಾತೆ|ಕ್ರೆಡಿಟ್ ಮಿತಿ|ಕ್ರೆಡಿಟ್ ಅವಧಿ|ಗ್ರೇಸ್ ಅವಧಿ (ದಿನಗಳು)|ಪ್ರಸ್ತುತ ಬಾಕಿ|ಲಭ್ಯವಿರುವ ಕ್ರೆಡಿಟ್|ಹೌದು|ಇಲ್ಲ|ತಿಂಗಳು|ಬಿಲ್|ರೋಗಿ|ಪರೀಕ್ಷೆಗಳು|ಬಿಲ್ ಮಾಡಿದ ಮೊತ್ತ|ಸಿದ್ಧ ವರದಿಗಳು|ಮೊತ್ತ",
 "ml": "ക്രെഡിറ്റ് വ്യവസ്ഥകൾ|സമീപകാല പേയ്‌മെന്റുകൾ|വിവരം|മൂല്യം|തീയതി|അടച്ചത്|രീതി|ശേഷമുള്ള ബാക്കി|ഇളവ്|ക്രെഡിറ്റ് അക്കൗണ്ട്|ക്രെഡിറ്റ് പരിധി|ക്രെഡിറ്റ് കാലയളവ്|ഗ്രേസ് കാലയളവ് (ദിവസം)|നിലവിലെ കുടിശ്ശിക|ലഭ്യമായ ക്രെഡിറ്റ്|അതെ|ഇല്ല|മാസം|ബിൽ|രോഗി|പരിശോധനകൾ|ബിൽ ചെയ്ത തുക|തയ്യാറായ റിപ്പോർട്ടുകൾ|തുക",
 "mr": "क्रेडिट अटी|अलीकडील पेमेंट|तपशील|मूल्य|तारीख|भरलेले|पद्धत|नंतरची थकबाकी|सवलत|क्रेडिट खाते|क्रेडिट मर्यादा|क्रेडिट कालावधी|ग्रेस कालावधी (दिवस)|सध्याची थकबाकी|उपलब्ध क्रेडिट|होय|नाही|महिना|बिल|रुग्ण|चाचण्या|बिल केलेली रक्कम|तयार अहवाल|रक्कम",
 "bn": "ক্রেডিট শর্তাবলী|সাম্প্রতিক পেমেন্ট|বিবরণ|মান|তারিখ|পরিশোধিত|পদ্ধতি|পরে বকেয়া|ছাড়|ক্রেডিট অ্যাকাউন্ট|ক্রেডিট সীমা|ক্রেডিট সময়কাল|গ্রেস পিরিয়ড (দিন)|বর্তমান বকেয়া|উপলব্ধ ক্রেডিট|হ্যাঁ|না|মাস|বিল|রোগী|পরীক্ষা|বিল করা পরিমাণ|প্রস্তুত রিপোর্ট|পরিমাণ",
 "gu": "ક્રેડિટ શરતો|તાજેતરની ચુકવણીઓ|વિગત|મૂલ્ય|તારીખ|ચૂકવેલ|રીત|પછીની બાકી રકમ|રાહત|ક્રેડિટ ખાતું|ક્રેડિટ મર્યાદા|ક્રેડિટ સમયગાળો|ગ્રેસ સમયગાળો (દિવસ)|હાલની બાકી રકમ|ઉપલબ્ધ ક્રેડિટ|હા|ના|મહિનો|બિલ|દર્દી|ટેસ્ટ|બિલ કરેલી રકમ|તૈયાર રિપોર્ટ|રકમ",
 "pa": "ਕ੍ਰੈਡਿਟ ਸ਼ਰਤਾਂ|ਹਾਲੀਆ ਅਦਾਇਗੀਆਂ|ਵੇਰਵਾ|ਮੁੱਲ|ਤਾਰੀਖ|ਅਦਾ ਕੀਤਾ|ਤਰੀਕਾ|ਬਾਅਦ ਦਾ ਬਕਾਇਆ|ਛੋਟ|ਕ੍ਰੈਡਿਟ ਖਾਤਾ|ਕ੍ਰੈਡਿਟ ਸੀਮਾ|ਕ੍ਰੈਡਿਟ ਮਿਆਦ|ਗ੍ਰੇਸ ਮਿਆਦ (ਦਿਨ)|ਮੌਜੂਦਾ ਬਕਾਇਆ|ਉਪਲਬਧ ਕ੍ਰੈਡਿਟ|ਹਾਂ|ਨਹੀਂ|ਮਹੀਨਾ|ਬਿੱਲ|ਮਰੀਜ਼|ਟੈਸਟ|ਬਿੱਲ ਕੀਤੀ ਰਕਮ|ਤਿਆਰ ਰਿਪੋਰਟਾਂ|ਰਕਮ",
 "ur": "کریڈٹ شرائط|حالیہ ادائیگیاں|تفصیل|قدر|تاریخ|ادا شدہ|طریقہ|بعد کا بقایا|رعایت|کریڈٹ اکاؤنٹ|کریڈٹ حد|کریڈٹ مدت|رعایتی مدت (دن)|موجودہ بقایا|دستیاب کریڈٹ|جی ہاں|نہیں|مہینہ|بل|مریض|ٹیسٹ|بل کی گئی رقم|تیار رپورٹیں|رقم",
 "or": "କ୍ରେଡିଟ୍ ସର୍ତ୍ତାବଳୀ|ସାମ୍ପ୍ରତିକ ପେମେଣ୍ଟ|ବିବରଣୀ|ମୂଲ୍ୟ|ତାରିଖ|ପରିଶୋଧିତ|ପଦ୍ଧତି|ପରେ ବକେୟା|ରିହାତି|କ୍ରେଡିଟ୍ ଖାତା|କ୍ରେଡିଟ୍ ସୀମା|କ୍ରେଡିଟ୍ ଅବଧି|ଗ୍ରେସ୍ ଅବଧି (ଦିନ)|ବର୍ତ୍ତମାନର ବକେୟା|ଉପଲବ୍ଧ କ୍ରେଡିଟ୍|ହଁ|ନା|ମାସ|ବିଲ୍|ରୋଗୀ|ପରୀକ୍ଷା|ବିଲ୍ ହୋଇଥିବା ରାଶି|ପ୍ରସ୍ତୁତ ରିପୋର୍ଟ|ରାଶି",
}
_LBL = {k: dict(zip([x.lower() for x in _LBL_EN], v.split("|"))) for k, v in _LBL.items()}


def _loc_table(tb, code):
    """Table headings, column names and row labels in the user's language: fixed word list, exact matches only, numbers/dates/names never touched."""
    try:
        m = _LBL.get(code)
        if not m or not isinstance(tb, dict):
            return tb
        def f(x):
            return m.get(x.strip().lower(), x) if isinstance(x, str) else x
        out = dict(tb)
        if "title" in out:
            out["title"] = f(out["title"])
        if isinstance(out.get("columns"), list):
            out["columns"] = [f(c) for c in out["columns"]]
        if isinstance(out.get("rows"), list):
            out["rows"] = [[f(c) for c in r] if isinstance(r, list) else r for r in out["rows"]]
        return out
    except Exception:
        return tb


def localize(res, lang, inst_code):
    """res: the /ask or B2B chat response dict. Returns a copy with 'answer' translated (original kept in 'answer_en')."""
    if not lang or not isinstance(res, dict):
        return res
    ans = res.get("answer")
    if not isinstance(ans, str) or not ans.strip() or res.get("status") not in ("success", None):
        return res
    import os as _os
    roman = len(lang) > 2 and lang[2] == "roman" and _os.getenv("SAHASRA_ROMAN_REPLY", "native").lower() == "roman"
    if not roman and _in_script(ans, lang[0]):        # the answer is already in the user's language
        out = dict(res)
        out["lang"] = lang[0]
        if not roman:
            for _k in ("table", "table2"):
                if isinstance(out.get(_k), dict):
                    out[_k] = _loc_table(out[_k], lang[0])
        return out
    t = _tm_translate(ans, lang[1], inst_code, roman, lang[0])
    if t is None:
        t = _translate(ans, lang[1], inst_code, roman=roman, code=lang[0])
    if t and _foreign(t):
        print("[lang] answer: foreign-script glitch, retrying", flush=True)
        t = _translate(ans, lang[1], inst_code, roman=roman, code=lang[0], strict=True)
        if t and _foreign(t):
            t = None
    if t and not (_nums(t) <= _nums(_iso_dates(ans))):        # invented a number: treat as lost
        print("[lang] answer: translation added numbers, retrying", flush=True)
        t = _translate(ans, lang[1], inst_code, roman=roman, code=lang[0], strict=True)
        if t and not (_nums(t) <= _nums(_iso_dates(ans))):
            t = None
    if t and not _nums(_iso_dates(ans)) <= _nums(t):        # never show a translation that lost a number: retry once, else keep English
        print("[lang] answer: translation lost numbers, retrying", flush=True)
        t = _translate(ans, lang[1], inst_code, roman=roman, code=lang[0], strict=True)
        if t and not _nums(_iso_dates(ans)) <= _nums(t):
            print("[lang] answer: still lost numbers, keeping English", flush=True)
            t = None
    if not t:        # the small model could not keep the numbers: one last try with the main model
        try:
            _FLAG.main_first = True
            t = _translate(ans, lang[1], inst_code, roman=roman, code=lang[0], strict=True)
        finally:
            _FLAG.main_first = False
        if t and not (_nums(_iso_dates(ans)) <= _nums(t) and _nums(t) <= _nums(_iso_dates(ans))):
            t = None
    if not t:
        return res
    out = dict(res)
    out["answer_en"], out["answer"], out["lang"] = ans, t, lang[0]
    if not roman:
        for _k in ("table", "table2"):
            if isinstance(out.get(_k), dict):
                out[_k] = _loc_table(out[_k], lang[0])
    return out


def inst_from_activation(code):
    try:
        from auth.license_service import validate_license
        v = validate_license((code or "").strip()) or {}
        return v.get("institution_code") or v.get("db_name")
    except Exception:
        return None
