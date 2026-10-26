"""b2b_langtest.py - checks that the B2B chat answers the SAME numbers in every supported language.
READ-ONLY: it only asks ordinary business questions (bills, totals, balance, credit, payments, services). No attacks, nothing that changes data.
Standard library only. Needs test-register ON (turn it OFF afterwards), same login as b2b_testplan.py.

  python b2b_langtest.py --api https://api.athentech.in --client CM --phone 9876543210 --org COMP0108
  python b2b_langtest.py ... --langs te,hi,ta        (only some languages)
  python b2b_langtest.py ... --quick                 (4 questions per language instead of 8)

How it judges each question (English is asked first and is the reference):
  PASS   = HTTP 200, reply is in the expected language, and every number in it also appears in the English reply (shorter answers are fine)
  FAIL   = error or wrong reply language.   (The AI-written English answers vary from run to run, so a number mismatch is only REVIEW.)
  REVIEW = the English reference itself had no numbers / could not answer (compare by eye)
Output: screen + b2b_langtest_results.csv.  The chat allows ~90 messages per 10 minutes, so the run is paced (~25 min for everything).
"""
import argparse, csv, json, re, time, unicodedata, urllib.request, urllib.error
ap = argparse.ArgumentParser(); ap.add_argument("--api", required=True); ap.add_argument("--client", required=True)
ap.add_argument("--phone", required=True); ap.add_argument("--org", default="COMP0108")
ap.add_argument("--langs", default="", help="comma list of: te,hi,ta,kn,ml,mr,bn,gu,pa,ur,or")
ap.add_argument("--quick", action="store_true"); ap.add_argument("--pace", type=float, default=7.0, help="seconds between questions")
a = ap.parse_args()
API = a.api.rstrip("/")

def http(path, body, token=None, timeout=150):
    req = urllib.request.Request(API + path, json.dumps(body).encode(), {"Content-Type": "application/json", **({"Authorization": "Bearer " + token} if token else {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r: return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        try: return e.code, json.loads(e.read().decode())
        except Exception: return e.code, {}
    except Exception as e: return 0, {"error": str(e)}

EN = {
 "A": "How many bills did I get this month?",
 "B": "How many bills did I get last month?",
 "C": "What is my total billed amount in the last 3 months?",
 "D": "What is my outstanding balance?",
 "E": "What is my credit limit?",
 "F": "When was my last payment and how much?",
 "G": "What services do you provide?",
 "H": "Has our payment been received?",
}
# language -> (native-script questions, English-letter questions). Same order as EN keys A..H; None = not tested.
L = {
 "te": ("Telugu", ["ఈ నెల ఎన్ని బిల్లులు వచ్చాయి?", "గత నెల ఎన్ని బిల్లులు వచ్చాయి?", "గత 3 నెలల్లో నా మొత్తం బిల్లు ఎంత?", "నా బకాయి మొత్తం ఎంత?", "నా క్రెడిట్ లిమిట్ ఎంత?", "నా చివరి చెల్లింపు ఎప్పుడు, ఎంత?", "మీరు ఏ ఏ సేవలు అందిస్తారు?", "మా చెల్లింపు అందిందా?"],
        ["ee nela enni bills ayyayi?", "gata nela enni bills ayyayi?", "gata 3 nelalo mottam entha bill ayyindi?", "naa baaki entha undi?", "naa credit limit entha?", "naa chivari payment eppudu, entha?", "meeru emi emi sevalu andhistharu?", "mana payment manaku vachindha?"]),
 "hi": ("Hindi", ["इस महीने कितने बिल बने?", "पिछले महीने कितने बिल बने?", "पिछले 3 महीनों में मेरी कुल बिल राशि कितनी है?", "मेरा बकाया कितना है?", "मेरी क्रेडिट लिमिट कितनी है?", "मेरा आखिरी भुगतान कब और कितना था?", "आप कौन सी सेवाएं देते हैं?", "क्या हमारा भुगतान मिल गया?"],
        ["is mahine kitne bills bane?", "pichle mahine kitne bills bane?", "pichle 3 mahine mein meri kul bill rashi kitni hai?", "mera bakaya kitna hai?", "meri credit limit kitni hai?", "mera aakhri payment kab aur kitna tha?", "aap kaun si services dete hain?", "kya hamara payment mil gaya?"]),
 "ta": ("Tamil", ["இந்த மாதம் எத்தனை பில்கள்?", "கடந்த மாதம் எத்தனை பில்கள்?", "கடந்த 3 மாதங்களில் என் மொத்த பில் தொகை எவ்வளவு?", "என் நிலுவைத் தொகை எவ்வளவு?", "என் கிரெடிட் லிமிட் எவ்வளவு?", "என் கடைசி பணம் செலுத்தல் எப்போது, எவ்வளவு?", "நீங்கள் என்ன சேவைகள் வழங்குகிறீர்கள்?", "எங்கள் பணம் கிடைத்ததா?"],
        ["indha maadham ethanai bills?", "kadantha maadham ethanai bills?", "kadantha 3 maadhathil en mottha bill thogai evlo?", "en niluvai thogai evlo?", "en credit limit evlo?", "en kadaisi payment eppodhu, evlo?", "neenga enna enna services tharinga?", "engal payment kidaithatha, enna?"]),
 "kn": ("Kannada", ["ಈ ತಿಂಗಳು ಎಷ್ಟು ಬಿಲ್‌ಗಳಾಗಿವೆ?", "ಕಳೆದ ತಿಂಗಳು ಎಷ್ಟು ಬಿಲ್‌ಗಳಾಗಿವೆ?", "ಕಳೆದ 3 ತಿಂಗಳಲ್ಲಿ ನನ್ನ ಒಟ್ಟು ಬಿಲ್ ಮೊತ್ತ ಎಷ್ಟು?", "ನನ್ನ ಬಾಕಿ ಮೊತ್ತ ಎಷ್ಟು?", "ನನ್ನ ಕ್ರೆಡಿಟ್ ಲಿಮಿಟ್ ಎಷ್ಟು?", "ನನ್ನ ಕೊನೆಯ ಪಾವತಿ ಯಾವಾಗ, ಎಷ್ಟು?", "ನೀವು ಯಾವ ಯಾವ ಸೇವೆಗಳನ್ನು ನೀಡುತ್ತೀರಿ?", "ನಮ್ಮ ಪಾವತಿ ಬಂದಿದೆಯೇ?"],
        ["ee tingalu eshtu bills aagide?", "kalede tingalu eshtu bills aagide?", "kalede 3 tingalalli nanna ottu bill mottha eshtu?", "nanna baaki mottha eshtu?", "nanna credit limit eshtu?", "nanna kone payment yavaga, eshtu?", "nimma yenu yenu services ide?", "namma payment bandideya, yenu?"]),
 "ml": ("Malayalam", ["ഈ മാസം എത്ര ബില്ലുകൾ ആയി?", "കഴിഞ്ഞ മാസം എത്ര ബില്ലുകൾ ആയി?", "കഴിഞ്ഞ 3 മാസത്തിൽ എന്റെ ആകെ ബിൽ തുക എത്ര?", "എന്റെ കുടിശ്ശിക എത്ര?", "എന്റെ ക്രെഡിറ്റ് ലിമിറ്റ് എത്ര?", "എന്റെ അവസാന പേയ്‌മെന്റ് എപ്പോൾ, എത്ര?", "നിങ്ങൾ എന്തൊക്കെ സേവനങ്ങൾ നൽകുന്നു?", "ഞങ്ങളുടെ പേയ്‌മെന്റ് കിട്ടിയോ?"],
        ["ee maasam ethra bills aayi?", "kazhinja maasam ethra bills aayi?", "kazhinja 3 maasathil ente aake bill thuka ethra?", "ente kudishika ethra?", "ente credit limit ethra?", "ente avasana payment eppol, ethra?", "ningal entokke services tharunnu?", "njangalude payment kittiyo, ethra?"]),
 "mr": ("Marathi", ["या महिन्यात किती बिल झाली?", "गेल्या महिन्यात किती बिल झाली?", "गेल्या 3 महिन्यांत माझी एकूण बिल रक्कम किती?", "माझी थकबाकी किती आहे?", "माझी क्रेडिट लिमिट किती आहे?", "माझे शेवटचे पेमेंट कधी आणि किती होते?", "तुम्ही कोणत्या सेवा देता, काय काय आहे?", "आमचे पेमेंट मिळाले का, किती आहे?"],
        ["ya mahinyat kiti bills jhale?", "gelya mahinyat kiti bills jhale?", "gelya 3 mahinyat majhi ekun bill rakkam kiti?", "majhi thakbaki kiti aahe?", "majhi credit limit kiti aahe?", "majhe shevtache payment kadhi ani kiti hote, sanga?", "tumhi kontya services deta, sanga?", "amche payment milale ka, kiti aahe?"]),
 "bn": ("Bengali", ["এই মাসে কয়টি বিল হয়েছে?", "গত মাসে কয়টি বিল হয়েছে?", "গত 3 মাসে আমার মোট বিলের পরিমাণ কত?", "আমার বকেয়া কত?", "আমার ক্রেডিট লিমিট কত?", "আমার শেষ পেমেন্ট কবে এবং কত ছিল?", "আপনারা কী কী সেবা দেন?", "আমাদের পেমেন্ট কি পাওয়া গেছে?"],
        ["ei mashe koto bill hoyeche?", "gato mashe koto bill hoyeche?", "gato 3 mashe amar mot biller poriman koto?", "amar bokeya koto?", "amar credit limit koto?", "amar shesh payment kobe ar koto chhilo?", "apnara ki ki service den, bolun?", "amader payment ki peyechen, bolun?"]),
 "gu": ("Gujarati", ["આ મહિને કેટલા બિલ થયા?", "ગયા મહિને કેટલા બિલ થયા?", "છેલ્લા 3 મહિનામાં મારી કુલ બિલ રકમ કેટલી છે?", "મારી બાકી રકમ કેટલી છે?", "મારી ક્રેડિટ લિમિટ કેટલી છે?", "મારું છેલ્લું પેમેન્ટ ક્યારે અને કેટલું હતું?", "તમે કઈ કઈ સેવાઓ આપો છો?", "અમારું પેમેન્ટ મળ્યું?"],
        ["aa mahine ketla bills thaya?", "pachla mahine ketla bills thaya?", "pachla 3 mahina ma mari kul bill rakam ketli chhe?", "mari baki rakam ketli chhe?", "mari credit limit ketli chhe?", "maru chhelu payment kyare ane ketlu hatu, batavo?", "tame shu shu services apo cho, batavo?", "amaru payment malyu, ketlu chhe?"]),
 "pa": ("Punjabi", ["ਇਸ ਮਹੀਨੇ ਕਿੰਨੇ ਬਿੱਲ ਬਣੇ?", "ਪਿਛਲੇ ਮਹੀਨੇ ਕਿੰਨੇ ਬਿੱਲ ਬਣੇ?", "ਪਿਛਲੇ 3 ਮਹੀਨਿਆਂ ਵਿੱਚ ਮੇਰੀ ਕੁੱਲ ਬਿੱਲ ਰਕਮ ਕਿੰਨੀ ਹੈ?", "ਮੇਰਾ ਬਕਾਇਆ ਕਿੰਨਾ ਹੈ?", "ਮੇਰੀ ਕ੍ਰੈਡਿਟ ਲਿਮਿਟ ਕਿੰਨੀ ਹੈ?", "ਮੇਰੀ ਆਖਰੀ ਅਦਾਇਗੀ ਕਦੋਂ ਅਤੇ ਕਿੰਨੀ ਸੀ?", "ਤੁਸੀਂ ਕਿਹੜੀਆਂ ਸੇਵਾਵਾਂ ਦਿੰਦੇ ਹੋ?", "ਸਾਡੀ ਅਦਾਇਗੀ ਮਿਲ ਗਈ?"],
        ["is mahine kinne bills bane?", "pichle mahine kinne bills bane?", "pichle 3 mahine vich meri kul bill rakam kinni hai?", "mera bakaya kinna hai?", "meri credit limit kinni hai?", "meri akhri payment kado te kinni si, dasso?", "tusi ki ki services dinde ho, dasso?", "sadi payment mil gayi, kinni hai?"]),
 "ur": ("Urdu", ["اس مہینے کتنے بل بنے؟", "پچھلے مہینے کتنے بل بنے؟", "پچھلے 3 مہینوں میں میری کل بل رقم کتنی ہے؟", "میرا بقایا کتنا ہے؟", "میری کریڈٹ لمٹ کتنی ہے؟", "میری آخری ادائیگی کب اور کتنی تھی؟", "آپ کون سی خدمات دیتے ہیں؟", "کیا ہماری ادائیگی مل گئی؟"],
        None),
 "or": ("Odia", ["ଏହି ମାସରେ କେତୋଟି ବିଲ୍ ହୋଇଛି?", "ଗତ ମାସରେ କେତୋଟି ବିଲ୍ ହୋଇଛି?", "ଗତ 3 ମାସରେ ମୋର ମୋଟ ବିଲ୍ ରାଶି କେତେ?", "ମୋର ବକେୟା କେତେ?", "ମୋର କ୍ରେଡିଟ୍ ଲିମିଟ୍ କେତେ?", "ମୋର ଶେଷ ପେମେଣ୍ଟ କେବେ ଏବଂ କେତେ ଥିଲା?", "ଆପଣ କେଉଁ ସେବା ଦିଅନ୍ତି?", "ଆମର ପେମେଣ୍ଟ ମିଳିଲା କି?"],
        ["ei masa re kete bill heichi?", "gata masa re kete bill heichi?", "gata 3 masa re mora mota bill rashi kete?", "mora bakeya kete?", "mora credit limit kete?", "mora sesh payment kebe ebam kete thila?", "apana kemiti services dena, dekhantu?", None]),
}
KEYS = list("ABCDEFGH")
if a.quick: KEYS = ["A", "C", "D", "G"]
wanted = [x.strip() for x in a.langs.split(",") if x.strip()] or list(L)
OKLANG = {"hi": {"hi", "ur"}, "ur": {"hi", "ur"}}
RANGES = {"hi": (0x900, 0x97F), "mr": (0x900, 0x97F), "bn": (0x980, 0x9FF), "pa": (0xA00, 0xA7F), "gu": (0xA80, 0xAFF), "or": (0xB00, 0xB7F),
          "ta": (0xB80, 0xBFF), "te": (0xC00, 0xC7F), "kn": (0xC80, 0xCFF), "ml": (0xD00, 0xD7F), "ur": (0x600, 0x6FF)}
def native_script(text, code):
    lo, hi = RANGES[code]
    letters = [c for c in text if c.isalpha()]
    return bool(letters) and sum(1 for c in letters if lo <= ord(c) <= hi) / len(letters) > 0.4

def flat(j):
    t = str((j or {}).get("answer", "") or "")
    tb = (j or {}).get("table") or {}
    if isinstance(tb, dict): t += " | " + " ; ".join(" / ".join(map(str, r)) for r in tb.get("rows", [])[:25])
    return re.sub(r"\s+", " ", t)
def nums(text):
    t = "".join(str(unicodedata.digit(c)) if c.isdigit() and not c.isascii() else c for c in text)
    t = re.sub(r"(?<=\d),(?=\d)", "", t)
    return sorted(set(re.findall(r"\d+(?:\.\d+)?", t)))
def ask(token, q):
    for _ in range(4):
        t0 = time.time()
        s, r = http("/public/b2b/chat", {"client": a.client, "message": q, "period": "this_month", "chat_history": []}, token)
        if s == 429: time.sleep(65); continue
        time.sleep(a.pace)
        return s, r, int((time.time() - t0) * 1000)
    return 429, {}, 0

s, j = http("/public/b2b/test-register", {"client": a.client, "phone": a.phone, "org_code": a.org, "name": "LangTest"})
if s != 200: raise SystemExit("test-register failed: %s %s (is the test-register switch ON?)" % (s, j))
s, j2 = http("/public/b2b/verify-otp", {"client": a.client, "phone": j["phone"], "code": j["test_code"]})
tok = j2.get("token") or j2.get("access_token")
if not tok: raise SystemExit("login failed: %s %s" % (s, j2))

rows, ref = [], {}
print("== English reference ==")
for k in KEYS:
    s, r, ms = ask(tok, EN[k]); ans = flat(r); ref[k] = (s, ans, nums(ans))
    print("%s %4d ms  %s\n      -> %s" % (k, ms, EN[k], ans[:200]))
    rows.append(["en", k, "script", EN[k], "REF", ms, "", ans])

summary = {}
for code in wanted:
    if code not in L: continue
    name, native, roman = L[code]
    for kind, qs in (("native", native), ("english-letters", roman)):
        if not qs: continue
        print("\n== %s (%s) ==" % (name, kind))
        for k in KEYS:
            q = qs[ord(k) - 65]
            if not q: continue
            s, r, ms = ask(tok, q); ans = flat(r); lang = (r or {}).get("lang") or "en"
            rs, rans, rn = ref[k]; why = []
            if s != 200: why.append("HTTP %s" % s)
            if re.search(r"(?i)traceback|query failed|internal error|unsupported period", ans): why.append("error text")
            script_ok = native_script(ans, code) if kind == "native" else False
            if lang not in OKLANG.get(code, {code}) and not script_ok: why.append("reply language '%s' (wanted %s)" % (lang, code))
            en_view = flat({"answer": (r or {}).get("answer_en") or ""}) if (r or {}).get("answer_en") else ""
            mine = nums(en_view or ans)
            note = ""
            if rn and mine and not set(mine) <= set(rn): note = "numbers not in the English answer: %s (English had %s)" % (sorted(set(mine) - set(rn))[:6], rn[:6])
            elif rn and not mine: note = "no numbers (English had %s)" % rn[:6]
            v = "FAIL" if why else ("REVIEW" if (note or not rn) else "PASS")
            if note: why.append(note)
            summary.setdefault((name, kind), []).append(v)
            rows.append([code, k, kind, q, v, ms, "; ".join(why), ans])
            print("%s %-6s %5d ms  %s%s\n      -> %s" % (k, v, ms, q, ("   [" + "; ".join(why) + "]") if why else "", ans[:220]))

with open("b2b_langtest_results.csv", "w", newline="", encoding="utf-8", errors="replace") as f:
    w = csv.writer(f); w.writerow(["lang", "q", "kind", "question", "verdict", "ms", "why", "answer"]); w.writerows(rows)
print("\n== Summary (PASS/FAIL/REVIEW) ==")
tp = tf = tr = 0
for (name, kind), vs in summary.items():
    p, f_, rv = vs.count("PASS"), vs.count("FAIL"), vs.count("REVIEW"); tp += p; tf += f_; tr += rv
    print("%-10s %-16s PASS %d  FAIL %d  REVIEW %d" % (name, kind, p, f_, rv))
print("TOTAL PASS %d  FAIL %d  REVIEW %d  -> b2b_langtest_results.csv" % (tp, tf, tr))
