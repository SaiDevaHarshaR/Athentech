"""Telugu / Hindi (and Telglish / Hinglish) -> plain English for the questions the assistant already understands.
Word-list based: no AI call, no cost, no delay. Unknown words are left as typed. Returns (text, changed)."""
import re

# distinctive words: if one of these (or any Telugu/Devanagari letter) is present the question is rewritten
_PHRASES = [
    # periods
    ("ee roju", "today"), ("e roju", "today"), ("ee rooju", "today"), ("eroju", "today"), ("ee rojuki", "today"), ("ivala", "today"), ("ivvala", "today"), ("aaj ka", "today"), ("aaj", "today"), ("aj ka", "today"),
    ("ninna", "yesterday"), ("ninne", "yesterday"), ("kal ka", "yesterday"), ("kal", "yesterday"),
    ("gata nela", "last month"), ("pichhle mahine", "last month"), ("pichle mahine", "last month"), ("pichhle mahine ka", "last month"), ("last mahine", "last month"),
    ("ee nela", "this month"), ("is mahine", "this month"), ("is mahine ka", "this month"),
    ("gata vaaram", "last week"), ("pichhle hafte", "last week"), ("pichle hafte", "last week"),
    ("ee vaaram", "this week"), ("is hafte", "this week"), ("is hafte ka", "this week"),
    # asking
    ("enni", "how many"), ("kitne", "how many"), ("kitni", "how many"), ("entha", "total"), ("kitna", "total"), ("kitna hua", "total"),
    ("chupinchu", "show"), ("chupinchandi", "show"), ("cheppu", "show"), ("cheppandi", "show"), ("dikhao", "show"), ("dikhaiye", "show"), ("batao", "show"), ("bataiye", "show"),
    # things
    ("rogulu", "patients"), ("mareez", "patients"), ("marij", "patients"), ("patients ki", "patients"),
    ("billulu", "bills"), ("bills ki", "bills"), ("amdani", "revenue"), ("adayam", "revenue"), ("collection ki", "collection"),
    ("reportlu", "reports"), ("pending ga", "pending"), ("baaki", "pending"), ("bakaya", "dues"),
    # native script
    ("ఈ రోజు", "today"), ("నిన్న", "yesterday"), ("గత నెల", "last month"), ("ఈ నెల", "this month"), ("గత వారం", "last week"), ("ఈ వారం", "this week"),
    ("ఎన్ని", "how many"), ("ఎంత", "total"), ("రోగులు", "patients"), ("పేషెంట్లు", "patients"), ("బిల్లులు", "bills"), ("కలెక్షన్", "collection"), ("రిపోర్టులు", "reports"),
    ("చూపించు", "show"), ("చెప్పు", "show"), ("డాక్టర్లు", "doctors"),
    ("आज", "today"), ("कल", "yesterday"), ("पिछले महीने", "last month"), ("इस महीने", "this month"), ("पिछले हफ्ते", "last week"), ("इस हफ्ते", "this week"),
    ("कितने", "how many"), ("कितनी", "how many"), ("कितना", "total"), ("मरीज", "patients"), ("बिल", "bills"), ("कलेक्शन", "collection"), ("रिपोर्ट", "reports"),
    ("डॉक्टर", "doctors"), ("दिखाओ", "show"), ("बताओ", "show"), ("दिखाइए", "show"), ("बताइए", "show"),
]

_PHRASES += [
    # --- Telugu (romanised): time
    ("ee sanvatsaram", "this year"), ("gata sanvatsaram", "last year"), ("ee year", "this year"), ("ippudu", "now"), ("ippativaraku", "so far"),
    ("ee madhyaahnam", "today"), ("indhu", "today"),
    # asking / ranking
    ("enti", "what"), ("emiti", "what"), ("evaru", "who"), ("ekkada", "where"), ("ekkuva", "highest"), ("takkuva", "lowest"), ("mottam", "total"),
    ("anni", "all"), ("ivvu", "show"), ("ivvandi", "show"), ("chudali", "show"), ("chupinchara", "show"), ("kavali", "show"), ("cheyyi", "show"),
    # things
    ("patientlu", "patients"), ("patientla", "patients"), ("billu", "bill"), ("collectionlu", "collections"), ("aadaayam", "revenue"), ("adaayam", "revenue"),
    ("doctorlu", "doctors"), ("testlu", "tests"), ("samplelu", "samples"), ("branchlu", "branches"), ("refundlu", "refunds"), ("discountlu", "discounts"),
    ("dabbulu", "amount"), ("dabbu", "amount"), ("baaki unna", "pending"), ("pending unna", "pending"), ("cancel ayina", "cancelled"),
    # --- Telugu (script)
    ("ఈరోజు", "today"), ("ఇవాళ", "today"), ("ఈ సంవత్సరం", "this year"), ("గత సంవత్సరం", "last year"), ("మొత్తం", "total"),
    ("బిల్లు", "bill"), ("కలెక్షన్లు", "collections"), ("ఆదాయం", "revenue"), ("పెండింగ్", "pending"), ("టెస్టులు", "tests"), ("చూపించండి", "show"),
    ("చెప్పండి", "show"), ("ఇవ్వండి", "show"), ("బ్రాంచ్", "branch"), ("శాంపిల్స్", "samples"), ("ఎవరు", "who"), ("ఎక్కడ", "where"),
    ("అన్ని", "all"), ("ఎక్కువ", "highest"), ("తక్కువ", "lowest"), ("డాక్టర్", "doctors"), ("రోగుల", "patients"), ("పేషెంట్", "patients"),
    # --- Hindi extras
    ("kul", "total"), ("sabse zyada", "highest"), ("sabse kam", "lowest"), ("kaun", "who"), ("kahan", "where"), ("kya hai", "what"),
    ("sab", "all"), ("baki", "pending"), ("baaki", "pending"), ("aamdani", "revenue"), ("kamai", "revenue"), ("nakad", "cash"),
    ("कुल", "total"), ("सबसे ज्यादा", "highest"), ("सबसे कम", "lowest"), ("पेंडिंग", "pending"), ("आमदनी", "revenue"), ("सभी", "all"), ("ब्रांच", "branch"),
]
# words that mean the glossary did not cover everything -> ask the AI to translate the rest
_LEFTOVER = set("""enti emiti evaru ekkada ela undi unnaru unnayi vachaaru vachayi tesukunna cheyyi cheyandi kavali chudali ivvandi cheppandi chupinchandi
 anni oka okka ee aa ika inka lo ki ku nundi nunchi tho toh gurinchi gurunchi kosam pampinchu ayyaru ayyindi poyindi poyayi vastunnaru
 kya hai hain kaun kahan kaise kaisa kitna kitne kitni mujhe humein hume dikhao batao zara thoda zyada kam sab saare""".split())

_FILLER = {"aaye", "aaya", "aayi", "hue", "hui", "vachaaru", "vachayi", "ka", "ki", "ke", "ko", "hai", "hain", "hua", "ayyindi", "ayyayi", "undi", "unnayi", "vachindi", "me", "mein", "lo", "yokka", "ni", "ku",
           "का", "की", "के", "को", "है", "हैं", "हुआ", "में", "కి", "లో", "ఉంది", "ఉన్నాయి", "ఎంత"}
_NATIVE = re.compile("[\u0900-\u097f\u0c00-\u0c7f]")
_PH = sorted(_PHRASES + [("eroju", "today"), ("aj", "today"), ("ivala", "today")], key=lambda p: -len(p[0]))


def _pat(key):
    """romanised spelling is loose: 'eeroju', 'ee-roju', 'eroju', 'aaj', 'aj' all mean the same word."""
    if not key.isascii():
        return re.escape(key)
    out = []
    for ch in key:
        if ch == " ":
            out.append(r"[\s\-]*")
        elif ch in "aeiou":
            out.append(ch + "+")
        else:
            out.append(re.escape(ch))
    return "".join(out)


_RX = [(re.compile(r"(?<![\w])" + _pat(a) + r"(?![\w])", re.I), b) for a, b in _PH]
_WEAK = ("kal", "aaj", "aj", "enni", "kal ka", "aaj ka", "aj ka")
_MARK = re.compile(r"(?<![\w])(" + "|".join(_pat(a) for a, _ in _PH if a.isascii() and a not in _WEAK) + r")(?![\w])", re.I)


def to_english(text):
    try:
        t = (text or "").strip()
        if not t or not (_NATIVE.search(t) or _MARK.search(t)):
            return t, False
        out = t
        for rx, rep in _RX:
            out = rx.sub(rep, out)
        words = [w for w in re.split(r"\s+", out) if w and w.lower() not in _FILLER]
        out = re.sub(r"\s+", " ", " ".join(words)).strip(" ?.,")
        if not out or out.lower() == t.lower():
            return t, False
        return out, True
    except Exception:
        return text, False


import os
import threading

_CACHE = {}
_SHIELD = re.compile(r"\d{5,}|\buhid\b|\bphone\b|\bmobile\b|\bpatient\s+(named|called)\b", re.I)
_PROMPT = ("You translate questions typed by hospital/laboratory staff in Telugu, Hindi, Telglish or Hinglish (any spelling) into ONE short plain English "
           "question for a hospital billing/lab reporting system. Keep branch names, doctor names, test names and numbers exactly as written. "
           "Output only the English question, nothing else.")


def _llm_translate(text, timeout=7.0):
    """One short AI call (question text only, never patient data). None on any problem."""
    if os.getenv("SAHASRA_LANG_LLM", "1") != "1" or _SHIELD.search(text):
        return None
    if text in _CACHE:
        return _CACHE[text]
    box = {}

    def work():
        try:
            from agent.agent import _get_provider_chain
            from langchain_core.messages import HumanMessage, SystemMessage
            for _name, model in _get_provider_chain():
                try:
                    r = model.invoke([SystemMessage(content=_PROMPT), HumanMessage(content=text)])
                    t = str(getattr(r, "content", r) or "").strip().strip('"').splitlines()[0].strip()
                    if t:
                        box["t"] = t
                        return
                except Exception:
                    continue
        except Exception:
            pass
    th = threading.Thread(target=work, daemon=True)
    th.start()
    th.join(timeout)
    t = box.get("t")
    if t and len(t) <= 300 and not _NATIVE.search(t):
        if len(_CACHE) > 500:
            _CACHE.clear()
        _CACHE[text] = t
        return t
    return None


def translate(text):
    """Word list first; if something is left over that the list could not cover, one short AI call. Returns (text, changed)."""
    try:
        out, ch = to_english(text)
        orig = (text or "").strip()
        if not ch and not _NATIVE.search(orig):
            return out, False
        left = _NATIVE.search(out) or any(w.lower().strip("?.,") in _LEFTOVER for w in out.split())
        if left:
            t = _llm_translate(orig)
            if t and t.lower() != orig.lower():
                return t, True
        return out, ch
    except Exception:
        return text, False
