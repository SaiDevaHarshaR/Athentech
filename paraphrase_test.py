"""Rephrased questions (Telugu + Hindi, native script + English letters) -> must contain the right fact. READ-ONLY, no tickets.
Writes paraphrase_result.csv after every question."""
import argparse, csv, json, re, time, unicodedata, urllib.request, urllib.error
ap = argparse.ArgumentParser(); ap.add_argument("--api", required=True); ap.add_argument("--client", required=True); ap.add_argument("--phone", required=True)
ap.add_argument("--org", default="COMP0108"); ap.add_argument("--pace", type=float, default=6.0); a = ap.parse_args(); API = a.api.rstrip("/")
def http(path, body, token=None):
    req = urllib.request.Request(API + path, json.dumps(body).encode(), {"Content-Type": "application/json", **({"Authorization": "Bearer " + token} if token else {})})
    try:
        with urllib.request.urlopen(req, timeout=150) as r: return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        try: return e.code, json.loads(e.read().decode())
        except Exception: return e.code, {}
    except Exception as e: return 0, {"error": str(e)}
# intent -> (expected text in the answer, [(language, kind, question), ...])
B = {
"outstanding": (["69747"], [("te","native","మేము ఎంత బాకీ ఉన్నాం?"),("te","native","ఇంకా ఎంత కట్టాలి?"),("te","roman","memu entha baaki unnamu"),("te","roman","inka entha kattali"),("te","roman","maaku inka entha baaki undi"),
    ("hi","native","हमें कितना पैसा देना है?"),("hi","native","बकाया रकम बताइए"),("hi","roman","humein kitna paisa dena hai"),("hi","roman","bakaya rakam batao")]),
"credit limit": (["70000"], [("te","native","మా క్రెడిట్ లిమిట్ ఎంతో చెప్పండి"),("te","native","క్రెడిట్ పరిమితి ఎంత ఉంది"),("te","roman","maa credit limit entho cheppandi"),("te","roman","credit limit entha undi"),("te","roman","maa credit limit enti"),
    ("hi","native","हमारी क्रेडिट लिमिट बताइए"),("hi","native","क्रेडिट सीमा कितनी है"),("hi","roman","hamari credit limit batao"),("hi","roman","credit limit kitni hai")]),
"last month bills": (["14575"], [("te","native","గత నెలలో మొత్తం ఎంత బిల్లింగ్ అయింది"),("te","native","పోయిన నెల బిల్లుల సంఖ్య ఎంత"),("te","roman","gata nelalo motham entha billing ayindi"),("te","roman","poyina nela bills entha"),("te","roman","gata nela mottam bills entha"),
    ("hi","native","पिछले महीने कुल कितना बिलिंग हुआ"),("hi","native","बीते महीने के बिल कितने हैं"),("hi","roman","pichle mahine kul kitna billing hua"),("hi","roman","beete mahine ke bill kitne hain")]),
"agreement expiry": (["2029"], [("te","native","మా ఒప్పందం ఎప్పటివరకు చెల్లుతుంది"),("te","native","కాంట్రాక్ట్ గడువు ఎప్పుడు అయిపోతుంది"),("te","roman","maa oppandam eppativaraku celluthundi"),("te","roman","contract gaduvu eppudu ayipothundi"),
    ("hi","native","हमारा कॉन्ट्रैक्ट कब तक वैध है"),("hi","native","एग्रीमेंट की समाप्ति तिथि क्या है"),("hi","roman","hamara contract kab tak valid hai"),("hi","roman","agreement kab expire hota hai")]),
"services": (["YASHODHA", "CMLTSF93"], [("te","native","మీ దగ్గర ఏఏ సదుపాయాలు ఉన్నాయి"),("te","native","మీరు మాకు ఏం సర్వీసులు ఇస్తారు"),("te","roman","mee daggara emi sadupayalu unnayi"),("te","roman","meeru maaku em services istharu"),("te","roman","meeru em services istaru"),
    ("hi","native","आप हमें क्या-क्या सुविधाएँ देते हैं"),("hi","native","आपकी सेवाएँ क्या हैं"),("hi","roman","aap hamein kya kya suvidhayein dete hain"),("hi","roman","aapki sevayein kya hain")]),
"pending tests": (["SMN26190600"], [("te","native","ఇంకా పూర్తి కాని పరీక్షలు ఏవి"),("te","native","పెండింగ్ టెస్టులు చూపించు"),("te","roman","inka purti kaani parikshalu evi"),("te","roman","pending testulu chupinchu"),("te","roman","pending ayina testulu enni"),
    ("hi","native","अभी कौन सी जाँचें पूरी नहीं हुईं"),("hi","native","लंबित जाँचें दिखाइए"),("hi","roman","abhi kaun si janchein poori nahi hui"),("hi","roman","pending tests dikhao")]),
"packages": (["PKG", "80"], [("te","native","హెల్త్ ప్యాకేజీల జాబితా చూపించండి"),("te","native","ఏ ప్యాకేజీలు ఉన్నాయి"),("te","roman","health packagelu chupinchandi"),("te","roman","e packagelu unnayi"),("te","roman","e health packages unnayi"),
    ("hi","native","हेल्थ पैकेज की लिस्ट दिखाइए"),("hi","native","कौन-कौन से पैकेज हैं"),("hi","roman","health package ki list dikhao"),("hi","roman","kaun kaun se package hain")]),
"top tests": (["THYROID"], [("te","native","ఎక్కువగా చేసే టెస్టులు ఏవి"),("te","native","ఎక్కువ ఆర్డర్ అయిన పరీక్షలు"),("te","roman","ekkuvaga chese testulu evi"),("te","roman","ekkuva order ayina parikshalu"),("te","roman","ekkuvaga order chesina testulu"),
    ("hi","native","सबसे ज्यादा कौन सा टेस्ट हुआ"),("hi","native","सबसे अधिक मंगाई गई जाँचें"),("hi","roman","sabse zyada kaun sa test hua"),("hi","roman","sabse adhik mangayi gayi janchein")]),
"busiest branch": (["Central"], [("te","native","ఏ బ్రాంచ్ నుండి ఎక్కువ బిల్లులు వచ్చాయి"),("te","native","ఎక్కువ పనిచేసిన బ్రాంచ్ ఏది"),("te","roman","e branch nundi ekkuva bills vachayi"),("te","roman","ekkuva pani chesina branch edi"),
    ("hi","native","किस शाखा से सबसे ज्यादा बिल आए"),("hi","native","सबसे व्यस्त ब्रांच कौन सी है"),("hi","roman","kis shakha se sabse zyada bill aaye"),("hi","roman","sabse busy branch kaun si hai")]),
"last payment": (["1000"], [("te","native","చివరిసారి ఎంత కట్టాం"),("te","native","ఆఖరి పేమెంట్ ఎప్పుడు జరిగింది"),("te","roman","chivarisari entha kattam"),("te","roman","aakhari payment eppudu jarigindi"),("te","roman","naa chivari payment entha"),
    ("hi","native","आखिरी बार कितना भुगतान किया"),("hi","native","हमने आखिरी पेमेंट कब किया"),("hi","roman","aakhri baar kitna bhugtan kiya"),("hi","roman","humne aakhri payment kab kiya")]),
}
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
s, j = http("/public/b2b/test-register", {"client": a.client, "phone": a.phone, "org_code": a.org, "name": "ParaTest"})
if s != 200: raise SystemExit("test-register failed %s %s" % (s, j))
s, j2 = http("/public/b2b/verify-otp", {"client": a.client, "phone": j["phone"], "code": j["test_code"]})
tok = j2.get("token") or j2.get("access_token")
if not tok: raise SystemExit("login failed")
OUT = open("paraphrase_result.csv", "w", encoding="utf-8-sig", newline=""); W = csv.writer(OUT); W.writerow(["intent", "lang", "kind", "question", "verdict", "answer"])
tot = ok = 0; per = {}
for intent, (exp, qs) in B.items():
    for lang, kind, q in qs:
        s, r = ask(tok, q); ans = flat(r); good = s == 200 and any(e.lower() in ans.lower() for e in exp)
        tot += 1; ok += good; per.setdefault((lang, kind), [0, 0]); per[(lang, kind)][1] += 1; per[(lang, kind)][0] += good
        v = "PASS" if good else "FAIL"; W.writerow([intent, lang, kind, q, v, ans[:300]]); OUT.flush()
        print("%-4s %-16s %-3s %-7s %s%s" % (v, intent, lang, kind, q, "" if good else "\n        -> " + ans[:160]), flush=True)
print("\nPASS %d of %d" % (ok, tot))
for k, (g, n) in sorted(per.items()): print("  %s %-7s %d/%d" % (k[0], k[1], g, n))
