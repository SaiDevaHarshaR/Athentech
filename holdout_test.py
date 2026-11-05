"""holdout_test.py - 10 questions x 9 languages x native/English letters (180), written in casual everyday wording that the agent was NEVER tuned on. Asks questions only; compares each with the English answer. Gives the honest pass rate.
  python -X utf8 holdout_test.py --api https://api.athentech.in --client CM --phone 9876543210 --org COMP0108"""
import argparse, csv, json, re, time, unicodedata, urllib.request, urllib.error
ap = argparse.ArgumentParser(); ap.add_argument("--api", required=True); ap.add_argument("--client", required=True); ap.add_argument("--phone", required=True)
ap.add_argument("--org", default="COMP0108"); ap.add_argument("--pace", type=float, default=6.0); ap.add_argument("--langs", default=""); a = ap.parse_args(); API = a.api.rstrip("/")
def http(path, body, token=None):
    req = urllib.request.Request(API + path, json.dumps(body).encode(), {"Content-Type": "application/json", **({"Authorization": "Bearer " + token} if token else {})})
    try:
        with urllib.request.urlopen(req, timeout=150) as r: return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        try: return e.code, json.loads(e.read().decode())
        except Exception: return e.code, {}
    except Exception as e: return 0, {"error": str(e)}

def flat(j):
    t = str((j or {}).get("answer", "") or ""); tb = (j or {}).get("table") or {}
    if isinstance(tb, dict): t += " | " + " ; ".join(" / ".join(map(str, r)) for r in tb.get("rows", [])[:60])
    t = "".join(str(unicodedata.digit(c)) if c.isdigit() and not c.isascii() else c for c in t)
    return re.sub(r"(?<=\d),(?=\d)", "", t)
def ask(tok, q):
    for _ in range(4):
        s, r = http("/public/b2b/chat", {"client": a.client, "message": q, "period": "this_month", "chat_history": []}, tok)
        if s == 429: time.sleep(65); continue
        time.sleep(a.pace); return s, r
    return 429, {}
s, j = http("/public/b2b/test-register", {"client": a.client, "phone": a.phone, "org_code": a.org, "name": "Lang9"})
if s != 200: raise SystemExit("test-register failed %s %s (is the test-register switch ON?)" % (s, j))
s, j2 = http("/public/b2b/verify-otp", {"client": a.client, "phone": j["phone"], "code": j["test_code"]})
tok = j2.get("token") or j2.get("access_token")
if not tok: raise SystemExit("login failed")
EN = {'A': 'What is my outstanding balance?', 'B': 'What is my credit limit?', 'C': 'How many bills did I get last month?', 'D': 'Which tests are still pending?', 'E': 'What is the price of CBC?', 'F': 'What health-check packages are available?', 'G': 'What is the status of my reports?', 'H': 'Has our payment been received?', 'I': 'Which tests were ordered most frequently?', 'J': 'When does our agreement expire?'}
NAME = {'A': 'outstanding', 'B': 'credit limit', 'C': 'last month bills', 'D': 'pending tests', 'E': 'CBC price', 'F': 'packages', 'G': 'report status', 'H': 'payment received', 'I': 'top tests', 'J': 'agreement expiry'}
DATA = """ta|A|இன்னும் எவ்வளவு பணம் கட்டணும் சொல்லுங்க|innum evlo panam kattanum sollunga
ta|B|எங்களுக்கு எவ்வளவு கிரெடிட் லிமிட் கொடுத்திருக்கீங்க|engalukku evlo credit limit koduthirukkeenga
ta|C|போன மாசம் எத்தன பில் போட்டிருக்கோம்|pona maasam ethana bill pottirukkom
ta|D|எந்த டெஸ்ட் ரிசல்ட் இன்னும் வரல|entha test result innum varala
ta|E|CBC டெஸ்ட் ரேட் எவ்வளவு|CBC test rate evlo
ta|F|என்னென்ன ஹெல்த் செக்கப் பேக்கேஜ் இருக்கு|ennenna health checkup package irukku
ta|G|எங்க ரிப்போர்ட் எல்லாம் ரெடியா|enga report ellam readya
ta|H|நாங்க கட்டின பணம் உங்களுக்கு வந்துச்சா|naanga kattina panam ungalukku vandhucha
ta|I|அதிகமா எந்த டெஸ்ட் பண்ணிருக்காங்க|adhigama entha test pannirukkaanga
ta|J|எங்க அக்ரிமெண்ட் எப்ப எக்ஸ்பயர் ஆகுது|enga agreement eppa expire aagudhu
kn|A|ಇನ್ನೂ ಎಷ್ಟು ದುಡ್ಡು ಕಟ್ಟಬೇಕು ಹೇಳಿ|innu eshtu duddu kattabeku heli
kn|B|ನಮಗೆ ಎಷ್ಟು ಕ್ರೆಡಿಟ್ ಲಿಮಿಟ್ ಕೊಟ್ಟಿದ್ದೀರಿ|namage eshtu credit limit kottiddiri
kn|C|ಹಿಂದಿನ ತಿಂಗಳು ಎಷ್ಟು ಬಿಲ್ ಮಾಡಿದ್ದೀರಿ|hindina tingalu eshtu bill madiddiri
kn|D|ಯಾವ ಟೆಸ್ಟ್ ರಿಸಲ್ಟ್ ಇನ್ನೂ ಬಂದಿಲ್ಲ|yava test result innu bandilla
kn|E|CBC ಟೆಸ್ಟ್ ರೇಟ್ ಎಷ್ಟು|CBC test rate eshtu
kn|F|ಯಾವ ಹೆಲ್ತ್ ಚೆಕಪ್ ಪ್ಯಾಕೇಜ್ ಇದೆ|yava health checkup package ide
kn|G|ನಮ್ಮ ರಿಪೋರ್ಟ್ ಎಲ್ಲಾ ರೆಡಿ ಆಗಿದೆಯಾ|namma report ella ready aagideya
kn|H|ನಾವು ಕಟ್ಟಿದ ದುಡ್ಡು ನಿಮಗೆ ಬಂತಾ|naavu kattida duddu nimage bantha
kn|I|ಹೆಚ್ಚಾಗಿ ಯಾವ ಟೆಸ್ಟ್ ಮಾಡಿಸ್ತಾರೆ|hecchaagi yava test madistaare
kn|J|ನಮ್ಮ ಅಗ್ರಿಮೆಂಟ್ ಯಾವಾಗ ಎಕ್ಸ್‌ಪೈರ್ ಆಗುತ್ತೆ|namma agreement yavaga expire aagutte
ml|A|ഇനി എത്ര രൂപ അടയ്ക്കാനുണ്ട് പറയൂ|ini ethra roopa adaykkanundu parayoo
ml|B|ഞങ്ങൾക്ക് എത്ര ക്രെഡിറ്റ് ലിമിറ്റ് തന്നിട്ടുണ്ട്|njangalkku ethra credit limit thannittundu
ml|C|കഴിഞ്ഞ മാസം എത്ര ബിൽ അടിച്ചു|kazhinja maasam ethra bill adichu
ml|D|ഏത് ടെസ്റ്റ് റിസൾട്ട് ഇതുവരെ വന്നിട്ടില്ല|ethu test result ithuvare vannittilla
ml|E|CBC ടെസ്റ്റിന് റേറ്റ് എത്രയാ|CBC testinu rate ethrayaa
ml|F|എന്തൊക്കെ ഹെൽത്ത് ചെക്കപ്പ് പാക്കേജ് ഉണ്ട്|enthokke health checkup package undu
ml|G|ഞങ്ങളുടെ റിപ്പോർട്ടുകൾ എല്ലാം റെഡിയായോ|njangalude reportukal ellam readyaayo
ml|H|ഞങ്ങൾ അടച്ച പൈസ നിങ്ങൾക്ക് കിട്ടിയോ|njangal adacha paisa ningalkku kittiyo
ml|I|കൂടുതലായി ഏത് ടെസ്റ്റാണ് ചെയ്യുന്നത്|koodudhalaayi ethu testaanu cheyyunnathu
ml|J|ഞങ്ങളുടെ എഗ്രിമെന്റ് എപ്പോഴാ കഴിയുന്നത്|njangalude agreement eppozhaa kazhiyunnathu
mr|A|अजून किती पैसे भरायचे आहेत सांगा|ajun kiti paise bharaiche aahet sanga
mr|B|आम्हाला किती क्रेडिट लिमिट दिलंय|amhala kiti credit limit dilay
mr|C|मागच्या महिन्यात किती बिल केली|maghchya mahinyat kiti bill keli
mr|D|कोणत्या टेस्टचा रिझल्ट अजून आला नाही|kontya testcha result ajun aala nahi
mr|E|CBC टेस्टचा रेट किती|CBC testcha rate kiti
mr|F|कोणती हेल्थ चेकअप पॅकेजेस आहेत|konti health checkup packages aahet
mr|G|आमचे सगळे रिपोर्ट तयार आहेत का|amche sagle report tayar aahet ka
mr|H|आम्ही भरलेले पैसे तुम्हाला मिळाले का|aamhi bharlele paise tumhala milale ka
mr|I|सगळ्यात जास्त कोणत्या टेस्ट होतात|sagalyat jast kontya test hotat
mr|J|आमचा अॅग्रीमेंट कधी एक्सपायर होतो|amcha agreement kadhi expire hoto
bn|A|আর কত টাকা দিতে হবে বলুন|ar koto taka dite hobe bolun
bn|B|আমাদের কত ক্রেডিট লিমিট দেওয়া আছে|amader koto credit limit deoa ache
bn|C|আগের মাসে কয়টা বিল করেছেন|ager mase koyta bill korechen
bn|D|কোন টেস্টের রেজাল্ট এখনও আসেনি|kon tester result ekhono asheni
bn|E|CBC টেস্টের রেট কত|CBC tester rate koto
bn|F|কী কী হেলথ চেকআপ প্যাকেজ আছে|ki ki health checkup package ache
bn|G|আমাদের সব রিপোর্ট কি রেডি|amader sob report ki ready
bn|H|আমরা যে টাকা দিয়েছি সেটা কি পেয়েছেন|amra je taka diyechi seta ki peyechen
bn|I|সবচেয়ে বেশি কোন টেস্ট হয়|sobcheye beshi kon test hoy
bn|J|আমাদের অ্যাগ্রিমেন্ট কবে এক্সপায়ার হবে|amader agreement kobe expire hobe
gu|A|હજી કેટલા પૈસા ભરવાના બાકી છે|haji ketla paisa bharvana baki chhe
gu|B|અમને કેટલી ક્રેડિટ લિમિટ આપી છે|amne ketli credit limit api chhe
gu|C|ગયા મહિને કેટલા બિલ બનાવ્યા|gaya mahine ketla bill banavya
gu|D|કયા ટેસ્ટનો રિઝલ્ટ હજી આવ્યો નથી|kya testno result haji aavyo nathi
gu|E|CBC ટેસ્ટનો રેટ કેટલો|CBC testno rate ketlo
gu|F|કયા હેલ્થ ચેકઅપ પેકેજ છે|kya health checkup package chhe
gu|G|અમારા બધા રિપોર્ટ તૈયાર છે|amara badha report taiyar chhe
gu|H|અમે ભરેલા પૈસા તમને મળ્યા|ame bharela paisa tamne malya
gu|I|સૌથી વધારે કયો ટેસ્ટ થાય છે|sauthi vadhare kayo test thay chhe
gu|J|અમારો એગ્રીમેન્ટ ક્યારે એક્સપાયર થશે|amaro agreement kyare expire thase
pa|A|ਹੋਰ ਕਿੰਨੇ ਪੈਸੇ ਦੇਣੇ ਨੇ ਦੱਸੋ|hor kinne paise dene ne dasso
pa|B|ਸਾਨੂੰ ਕਿੰਨੀ ਕ੍ਰੈਡਿਟ ਲਿਮਿਟ ਮਿਲੀ ਹੈ|sanu kinni credit limit mili hai
pa|C|ਪਿਛਲੇ ਮਹੀਨੇ ਕਿੰਨੇ ਬਿੱਲ ਕੀਤੇ|pichle mahine kinne bill kite
pa|D|ਕਿਹੜੇ ਟੈਸਟ ਦਾ ਰਿਜ਼ਲਟ ਅਜੇ ਨਹੀਂ ਆਇਆ|kihde test da result ajje nahi aaya
pa|E|CBC ਟੈਸਟ ਦਾ ਰੇਟ ਕਿੰਨਾ ਹੈ|CBC test da rate kinna hai
pa|F|ਕਿਹੜੇ ਹੈਲਥ ਚੈੱਕਅਪ ਪੈਕੇਜ ਹਨ|kihde health checkup package han
pa|G|ਸਾਡੀਆਂ ਸਾਰੀਆਂ ਰਿਪੋਰਟਾਂ ਤਿਆਰ ਨੇ|sadian sarian reportan tiyar ne
pa|H|ਜੋ ਪੈਸੇ ਅਸੀਂ ਦਿੱਤੇ ਉਹ ਤੁਹਾਨੂੰ ਮਿਲ ਗਏ|jo paise asin ditte oh tuhanu mil gaye
pa|I|ਸਭ ਤੋਂ ਜ਼ਿਆਦਾ ਕਿਹੜਾ ਟੈਸਟ ਹੁੰਦਾ ਹੈ|sab ton ziada kihda test hunda hai
pa|J|ਸਾਡਾ ਐਗਰੀਮੈਂਟ ਕਦੋਂ ਐਕਸਪਾਇਰ ਹੋਵੇਗਾ|sada agreement kado expire hovega
ur|A|ابھی کتنے پیسے دینے ہیں بتائیں|abhi kitne paise dene hain batayen
ur|B|ہمیں کتنی کریڈٹ لمٹ دی گئی ہے|hamen kitni credit limit di gayi hai
ur|C|پچھلے مہینے کتنے بل بنائے|pichle mahine kitne bill banaye
ur|D|کس ٹیسٹ کا رزلٹ ابھی تک نہیں آیا|kis test ka result abhi tak nahin aaya
ur|E|CBC ٹیسٹ کا ریٹ کیا ہے|CBC test ka rate kya hai
ur|F|کون سے ہیلتھ چیک اپ پیکجز ہیں|kaun se health checkup packages hain
ur|G|ہماری سب رپورٹس تیار ہیں|hamari sab reports tayyar hain
ur|H|ہم نے جو پیسے دیے وہ آپ کو مل گئے|hum ne jo paise diye woh aap ko mil gaye
ur|I|سب سے زیادہ کون سا ٹیسٹ ہوتا ہے|sab se zyada kaun sa test hota hai
ur|J|ہمارا ایگریمنٹ کب ایکسپائر ہوگا|hamara agreement kab expire hoga
or|A|ଆଉ କେତେ ଟଙ୍କା ଦେବାକୁ ହେବ କୁହନ୍ତୁ|aau kete tanka debaku hebe kuhantu
or|B|ଆମକୁ କେତେ କ୍ରେଡିଟ୍ ଲିମିଟ୍ ଦିଆଯାଇଛି|amaku kete credit limit diajaichhi
or|C|ଗତ ମାସରେ କେତୋଟି ବିଲ୍ କରିଥିଲେ|gata masare ketoti bill karithile
or|D|କେଉଁ ଟେଷ୍ଟର ରିଜଲ୍ଟ ଏବେ ଆସିନାହିଁ|keunthi testara result ebe asinahin
or|E|CBC ଟେଷ୍ଟର ରେଟ୍ କେତେ|CBC testara rate kete
or|F|କେଉଁ ହେଲ୍ଥ ଚେକଅପ୍ ପ୍ୟାକେଜ୍ ଅଛି|keu health checkup package achhi
or|G|ଆମର ସବୁ ରିପୋର୍ଟ ତିଆରି ହେଲାକି|amara sabu report tiari helaki
or|H|ଆମେ ଦେଇଥିବା ଟଙ୍କା ଆପଣଙ୍କୁ ମିଳିଲା କି|ame deithiba tanka apananku milila ki
or|I|ସବୁଠାରୁ ଅଧିକ କେଉଁ ଟେଷ୍ଟ ହୁଏ|sabuthaaru adhika keu test hue
or|J|ଆମର ଏଗ୍ରିମେଣ୍ଟ କେବେ ଏକ୍ସପାଏର ହେବ|amara agreement kebe expire hebe"""
RANGE = {"ta": (0x0B80, 0x0BFF), "kn": (0x0C80, 0x0CFF), "ml": (0x0D00, 0x0D7F), "mr": (0x0900, 0x097F), "bn": (0x0980, 0x09FF), "gu": (0x0A80, 0x0AFF), "pa": (0x0A00, 0x0A7F), "ur": (0x0600, 0x06FF), "or": (0x0B00, 0x0B7F)}
ALLR = list(RANGE.values()) + [(0x0C00, 0x0C7F)]
def script_ok(code, ans):
    lo, hi = RANGE[code]; sent = ans.split(" | ")[0].replace("\u0964", "").replace("\u0965", "")
    mine = sum(1 for c in sent if lo <= ord(c) <= hi); other = sum(1 for c in sent if any(l <= ord(c) <= h for l, h in ALLR) and not (lo <= ord(c) <= hi))
    if code in ("mr", "ur", "pa"): other -= sum(1 for c in sent if 0x0900 <= ord(c) <= 0x097F)
    return mine >= 2 and other <= max(1, mine // 10)
def script_not_wrong(code, ans):
    if code == "pa" and sum(1 for c in ans.split(" | ")[0] if 0x0900 <= ord(c) <= 0x097F) >= 2 and not any(0x0A00 <= ord(c) <= 0x0A7F for c in ans.split(" | ")[0]): return True
    lo, hi = RANGE[code]; sent = ans.split(" | ")[0].replace("\u0964", "").replace("\u0965", "")
    other = sum(1 for c in sent if any(l <= ord(c) <= h for l, h in ALLR) and not (lo <= ord(c) <= hi))
    if code in ("mr", "ur", "pa"): other -= sum(1 for c in sent if 0x0900 <= ord(c) <= 0x097F)
    return other <= 1
def nums(t): return set(x for x in re.findall(r"\d[\d.]*", t) if len(x.strip(".")) >= 2)
truth = {}
for k, q in EN.items():
    for _try in range(4):                      # the English baseline must itself be a real answer, not a "clarify"/empty reply
        s, r = ask(tok, q)
        if r.get("intent") not in ("clarify", None, "") and flat(r): break
        time.sleep(6)
    truth[k] = (r.get("intent"), nums(flat(r)), flat(r)[:120]); print("EN   %-18s intent=%s numbers=%d" % (NAME[k], truth[k][0], len(truth[k][1])), flush=True)
bank = []
for ln in DATA.splitlines():
    c, k, n, r = ln.split("|"); bank.append((c, k, "native", n)); bank.append((c, k, "english-letters", r))
OUT = open("holdout_result.csv", "w", encoding="utf-8-sig", newline=""); W = csv.writer(OUT); W.writerow(["lang", "kind", "topic", "question", "verdict", "why", "answer"])
good = []; bad = []; per = {}
for code, k, kind, q in bank:
    time.sleep(3)                                  # pace the questions: the Groq quota (429) was running out mid-test
    s, r = ask(tok, q); ans = flat(r); ti, tn, _ = truth[k]; why = []
    if s != 200: why.append("http %s" % s)
    _same = {r.get("intent"), ti} <= {"pending", "status"}      # this org has 0 pending: "no pending" and "all ready" say the same thing
    _nok = bool(tn) and len(tn & nums(ans)) >= max(1, len(tn) // 2)      # same facts as the English answer
    if r.get("intent") != ti and not _same and not _nok: why.append("intent %s (English gives %s)" % (r.get("intent"), ti))
    if tn and not _same and not _nok: why.append("numbers differ")
    if kind == "native" and not script_ok(code, ans): why.append("reply not in the user's language")
    if kind != "native" and not script_not_wrong(code, ans): why.append("reply in a different Indian language")
    ok = not why; per.setdefault((code, kind), [0, 0]); per[(code, kind)][1] += 1; per[(code, kind)][0] += ok
    (good if ok else bad).append((code, kind, k, q, "; ".join(why)))
    W.writerow([code, kind, NAME[k], q, "PASS" if ok else "FAIL", "; ".join(why), ans[:300]]); OUT.flush()
    print("%-4s %-3s %-15s %-16s %s%s" % ("PASS" if ok else "FAIL", code, kind, NAME[k], q, "" if ok else "\n        -> " + "; ".join(why) + " | " + ans[:110]), flush=True)
names = {"ta": "TAMIL", "kn": "KANNADA", "ml": "MALAYALAM", "mr": "MARATHI", "bn": "BENGALI", "gu": "GUJARATI", "pa": "PUNJABI", "ur": "URDU", "or": "ODIA"}
with open("sahasra_HOLDOUT_report.txt", "w", encoding="utf-8") as f:
    f.write("SAHASRA AI AGENT - HOLD-OUT TEST (everyday wording the agent was never tuned on). Questions that passed:\n\n")
    for c in names:
        g = [x for x in good if x[0] == c]
        f.write("=== %s (%d confirmed) ===\n" % (names[c], len(g)))
        for kind, t in (("native", "native script"), ("english-letters", "English letters")):
            f.write("  -- %s --\n" % t)
            for x in g:
                if x[1] == kind: f.write("     %-18s %s\n" % (NAME[x[2]], x[3]))
        f.write("\n")
print("\nPASSED %d of %d  (%.0f%%)" % (len(good), len(bank), 100.0 * len(good) / max(1, len(bank))))
for _k in ("native", "english-letters"):
    _n = sum(v[1] for kk, v in per.items() if kk[1] == _k); _p = sum(v[0] for kk, v in per.items() if kk[1] == _k)
    print("  %-16s %d/%d  (%.0f%%)" % (_k, _p, _n, 100.0 * _p / max(1, _n)))
for key in sorted(per): print("  %s %-16s %d/%d" % (key[0], key[1], per[key][0], per[key][1]))
