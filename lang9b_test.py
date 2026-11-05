"""lang9b_test.py - 14 more questions x 9 languages, native script and English letters (252 questions). Asks questions only.
Each question is compared with the answer to the SAME question in English on your server: same handler (intent), same numbers, and the reply must be in the user's own language.
  python -X utf8 lang9b_test.py --api https://api.athentech.in --client CM --phone 9876543210 --org COMP0108"""
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
EN = {'A': 'How many bills did I get this month?', 'B': 'How many invoices this month?', 'C': 'What is the status of my reports?', 'D': 'Which of my reports are pending?', 'E': 'Which orders are likely to be delayed?', 'F': 'What percentage of reports met TAT this month?', 'G': 'What is our sample rejection percentage?', 'H': "Compare our last three months' invoices.", 'I': 'What is the price and report time for CBC?', 'J': 'Show rejected samples', 'K': 'Top 10 recent bills', 'L': 'Billing total this month', 'M': 'Contract agreement details', 'N': 'Payment status'}
NAME = {'A': 'bills this month', 'B': 'invoices this month', 'C': 'report status', 'D': 'reports pending', 'E': 'delayed orders', 'F': 'TAT percent', 'G': 'sample rejection', 'H': 'compare 3 months', 'I': 'CBC price+time', 'J': 'rejected samples', 'K': 'top 10 bills', 'L': 'billing total', 'M': 'contract details', 'N': 'payment status'}
DATA = """ta|A|இந்த மாதம் எத்தனை பில்கள்?|intha maadham ethanai bills?
ta|B|இந்த மாதம் எத்தனை இன்வாய்ஸ்கள்?|intha maadham ethanai invoices?
ta|C|என் ரிப்போர்ட்களின் நிலை என்ன?|en reports nilai enna?
ta|D|எந்த ரிப்போர்ட்கள் நிலுவையில் உள்ளன?|entha reports niluvaiyil irukku?
ta|E|எந்த ஆர்டர்கள் தாமதமாகலாம்?|entha orders thamadhamagalam?
ta|F|இந்த மாதம் எத்தனை சதவீத ரிப்போர்ட்கள் TAT-க்குள் வந்தன?|intha maadham ethanai sathaveedham reports TAT kulle vandhana?
ta|G|எங்கள் சாம்பிள் நிராகரிப்பு சதவீதம் என்ன?|engal sample niraakarippu sathaveedham enna?
ta|H|கடந்த மூன்று மாத இன்வாய்ஸ்களை ஒப்பிடுங்கள்.|kadantha moondru maadha invoices oppidungal.
ta|I|CBC விலை மற்றும் ரிப்போர்ட் நேரம் என்ன?|CBC vilai matrum report neram enna?
ta|J|நிராகரிக்கப்பட்ட சாம்பிள்களைக் காட்டுங்கள்.|niraakarikkappatta samples kaattungal.
ta|K|என் சமீபத்திய 10 பில்களைக் காட்டுங்கள்.|en sameepathiya 10 bills kaattungal.
ta|L|இந்த மாதம் என் மொத்த பில்லிங் எவ்வளவு?|intha maadham en mottha billing evlo?
ta|M|ஒப்பந்த விவரங்களைக் காட்டுங்கள்.|oppanda vivarangalai kaattungal.
ta|N|பணம் செலுத்தும் நிலை என்ன?|panam seluthum nilai enna?
kn|A|ಈ ತಿಂಗಳು ಎಷ್ಟು ಬಿಲ್‌ಗಳಾಗಿವೆ?|ee tingalu eshtu bills aagide?
kn|B|ಈ ತಿಂಗಳು ಎಷ್ಟು ಇನ್‌ವಾಯ್ಸ್‌ಗಳಾಗಿವೆ?|ee tingalu eshtu invoices aagide?
kn|C|ನನ್ನ ರಿಪೋರ್ಟ್‌ಗಳ ಸ್ಥಿತಿ ಏನು?|nanna reports sthiti enu?
kn|D|ಯಾವ ರಿಪೋರ್ಟ್‌ಗಳು ಬಾಕಿ ಇವೆ?|yava reports baki ive?
kn|E|ಯಾವ ಆರ್ಡರ್‌ಗಳು ತಡವಾಗುವ ಸಾಧ್ಯತೆ ಇದೆ?|yava orders tadavaaguva saadhyate ide?
kn|F|ಈ ತಿಂಗಳು ಎಷ್ಟು ಶೇಕಡಾ ರಿಪೋರ್ಟ್‌ಗಳು TAT ಒಳಗೆ ಬಂದಿವೆ?|ee tingalu eshtu shekada reports TAT olage bandive?
kn|G|ನಮ್ಮ ಸ್ಯಾಂಪಲ್ ತಿರಸ್ಕಾರ ಶೇಕಡಾವಾರು ಎಷ್ಟು?|namma sample tiraskara shekadavaru eshtu?
kn|H|ಕಳೆದ ಮೂರು ತಿಂಗಳ ಇನ್‌ವಾಯ್ಸ್‌ಗಳನ್ನು ಹೋಲಿಸಿ.|kalede mooru tingala invoices holisi.
kn|I|CBC ಬೆಲೆ ಮತ್ತು ರಿಪೋರ್ಟ್ ಸಮಯ ಎಷ್ಟು?|CBC bele mattu report samaya eshtu?
kn|J|ತಿರಸ್ಕೃತ ಸ್ಯಾಂಪಲ್‌ಗಳನ್ನು ತೋರಿಸಿ.|tiraskruta samples toorisi.
kn|K|ನನ್ನ ಇತ್ತೀಚಿನ 10 ಬಿಲ್‌ಗಳನ್ನು ತೋರಿಸಿ.|nanna ittichina 10 bills toorisi.
kn|L|ಈ ತಿಂಗಳ ನನ್ನ ಒಟ್ಟು ಬಿಲ್ಲಿಂಗ್ ಎಷ್ಟು?|ee tingala nanna ottu billing eshtu?
kn|M|ಒಪ್ಪಂದದ ವಿವರಗಳನ್ನು ತೋರಿಸಿ.|oppandada vivaragalannu toorisi.
kn|N|ಪಾವತಿಯ ಸ್ಥಿತಿ ಏನು?|paavatiya sthiti enu?
ml|A|ഈ മാസം എത്ര ബില്ലുകൾ ആയി?|ee maasam ethra bills aayi?
ml|B|ഈ മാസം എത്ര ഇൻവോയ്സുകൾ ആയി?|ee maasam ethra invoices aayi?
ml|C|എന്റെ റിപ്പോർട്ടുകളുടെ സ്ഥിതി എന്താണ്?|ente reportukalude sthithi enthanu?
ml|D|ഏത് റിപ്പോർട്ടുകൾ ബാക്കിയാണ്?|ethu reportukal baakiyanu?
ml|E|ഏത് ഓർഡറുകൾ വൈകാൻ സാധ്യതയുണ്ട്?|ethu orderukal vaikan saadhyathayundu?
ml|F|ഈ മാസം എത്ര ശതമാനം റിപ്പോർട്ടുകൾ TAT-നുള്ളിൽ വന്നു?|ee maasam ethra shathamanam reportukal TAT nullil vannu?
ml|G|ഞങ്ങളുടെ സാമ്പിൾ നിരസിക്കൽ ശതമാനം എത്ര?|njangalude sample nirasikkal shathamanam ethra?
ml|H|കഴിഞ്ഞ മൂന്ന് മാസത്തെ ഇൻവോയ്സുകൾ താരതമ്യം ചെയ്യൂ.|kazhinja moonnu maasathe invoicukal tharathamyam cheyyoo.
ml|I|CBC വിലയും റിപ്പോർട്ട് സമയവും എത്ര?|CBC vilayum report samayavum ethra?
ml|J|നിരസിച്ച സാമ്പിളുകൾ കാണിക്കൂ.|nirasicha samplukal kaanikkoo.
ml|K|എന്റെ ഏറ്റവും പുതിയ 10 ബില്ലുകൾ കാണിക്കൂ.|ente ettavum puthiya 10 billukal kaanikkoo.
ml|L|ഈ മാസത്തെ എന്റെ ആകെ ബില്ലിംഗ് എത്ര?|ee maasathe ente aake billing ethra?
ml|M|കരാർ വിവരങ്ങൾ കാണിക്കൂ.|karar vivarangal kaanikkoo.
ml|N|പേയ്‌മെന്റ് സ്ഥിതി എന്താണ്?|payment sthithi enthanu?
mr|A|या महिन्यात किती बिल झाली?|ya mahinyat kiti bills jhale?
mr|B|या महिन्यात किती इनव्हॉइस झाले?|ya mahinyat kiti invoice jhale?
mr|C|माझ्या रिपोर्टची स्थिती काय आहे?|majhya reportchi sthiti kay aahe?
mr|D|कोणते रिपोर्ट बाकी आहेत?|konte report baki aahet?
mr|E|कोणत्या ऑर्डर उशिरा होण्याची शक्यता आहे?|kontya order ushira honyachi shakyata aahe?
mr|F|या महिन्यात किती टक्के रिपोर्ट TAT मध्ये आले?|ya mahinyat kiti takke report TAT madhe aale?
mr|G|आमचे सॅम्पल रिजेक्शन टक्केवारी किती आहे?|amche sample rejection takkevari kiti aahe?
mr|H|मागील तीन महिन्यांच्या इनव्हॉइसची तुलना करा.|maghil teen mahinyanchya invoice chi tulna kara.
mr|I|CBC ची किंमत आणि रिपोर्ट वेळ किती?|CBC chi kimmat ani report vel kiti?
mr|J|नाकारलेले सॅम्पल दाखवा.|nakarlele sample dakhva.
mr|K|माझी अलीकडील 10 बिले दाखवा.|majhi alikadil 10 bile dakhva.
mr|L|या महिन्यातील माझे एकूण बिलिंग किती?|ya mahinyatil majhe ekun billing kiti?
mr|M|कराराचे तपशील दाखवा.|karrache tapshil dakhva.
mr|N|पेमेंटची स्थिती काय आहे?|paymentchi sthiti kay aahe?
bn|A|এই মাসে কয়টি বিল হয়েছে?|ei mashe koyti bill hoyeche?
bn|B|এই মাসে কয়টি ইনভয়েস হয়েছে?|ei mashe koyti invoice hoyeche?
bn|C|আমার রিপোর্টের অবস্থা কী?|amar reporter obostha ki?
bn|D|কোন রিপোর্টগুলো বাকি আছে?|kon reportgulo baki ache?
bn|E|কোন অর্ডারগুলো দেরি হতে পারে?|kon ordergulo deri hote pare?
bn|F|এই মাসে কত শতাংশ রিপোর্ট TAT-এর মধ্যে এসেছে?|ei mashe koto shotangsho report TAT er moddhe eseche?
bn|G|আমাদের স্যাম্পল বাতিলের শতাংশ কত?|amader sample batiler shotangsho koto?
bn|H|গত তিন মাসের ইনভয়েস তুলনা করুন।|gato tin masher invoice tulona korun.
bn|I|CBC এর দাম ও রিপোর্টের সময় কত?|CBC er dam o reporter somoy koto?
bn|J|বাতিল স্যাম্পলগুলো দেখান।|batil samplegulo dekhan.
bn|K|আমার সাম্প্রতিক 10টি বিল দেখান।|amar samprotik 10ti bill dekhan.
bn|L|এই মাসে আমার মোট বিলিং কত?|ei mashe amar mot billing koto?
bn|M|চুক্তির বিবরণ দেখান।|chuktir biboron dekhan.
bn|N|পেমেন্টের অবস্থা কী?|paymenter obostha ki?
gu|A|આ મહિને કેટલા બિલ થયા?|aa mahine ketla bills thaya?
gu|B|આ મહિને કેટલા ઇન્વોઇસ થયા?|aa mahine ketla invoice thaya?
gu|C|મારા રિપોર્ટની સ્થિતિ શું છે?|mara reportni sthiti shu chhe?
gu|D|કયા રિપોર્ટ બાકી છે?|kya report baki chhe?
gu|E|કયા ઓર્ડર મોડા થવાની શક્યતા છે?|kya order moda thavani shakyata chhe?
gu|F|આ મહિને કેટલા ટકા રિપોર્ટ TAT માં આવ્યા?|aa mahine ketla taka report TAT ma aavya?
gu|G|અમારા સેમ્પલ રિજેક્શનની ટકાવારી કેટલી છે?|amara sample rejectionni takavari ketli chhe?
gu|H|છેલ્લા ત્રણ મહિનાના ઇન્વોઇસની સરખામણી કરો.|chhella tran mahinana invoice ni sarkhamni karo.
gu|I|CBC ની કિંમત અને રિપોર્ટ સમય કેટલો છે?|CBC ni kimmat ane report samay ketlo chhe?
gu|J|નકારાયેલા સેમ્પલ બતાવો.|nakarayela sample batavo.
gu|K|મારા તાજેતરના 10 બિલ બતાવો.|mara tajetarna 10 bill batavo.
gu|L|આ મહિનાનું મારું કુલ બિલિંગ કેટલું છે?|aa mahinanu maru kul billing ketlu chhe?
gu|M|કરારની વિગતો બતાવો.|kararni vigato batavo.
gu|N|પેમેન્ટની સ્થિતિ શું છે?|paymentni sthiti shu chhe?
pa|A|ਇਸ ਮਹੀਨੇ ਕਿੰਨੇ ਬਿੱਲ ਬਣੇ?|is mahine kinne bills bane?
pa|B|ਇਸ ਮਹੀਨੇ ਕਿੰਨੇ ਇਨਵੌਇਸ ਬਣੇ?|is mahine kinne invoice bane?
pa|C|ਮੇਰੀਆਂ ਰਿਪੋਰਟਾਂ ਦੀ ਸਥਿਤੀ ਕੀ ਹੈ?|merian reportan di sthiti ki hai?
pa|D|ਕਿਹੜੀਆਂ ਰਿਪੋਰਟਾਂ ਬਾਕੀ ਹਨ?|kihdian reportan baki han?
pa|E|ਕਿਹੜੇ ਆਰਡਰ ਲੇਟ ਹੋ ਸਕਦੇ ਹਨ?|kihde order late ho sakde han?
pa|F|ਇਸ ਮਹੀਨੇ ਕਿੰਨੇ ਪ੍ਰਤੀਸ਼ਤ ਰਿਪੋਰਟਾਂ TAT ਵਿੱਚ ਆਈਆਂ?|is mahine kinne pratishat reportan TAT vich aaian?
pa|G|ਸਾਡੇ ਸੈਂਪਲ ਰੱਦ ਹੋਣ ਦੀ ਪ੍ਰਤੀਸ਼ਤ ਕਿੰਨੀ ਹੈ?|sade sample radd hon di pratishat kinni hai?
pa|H|ਪਿਛਲੇ ਤਿੰਨ ਮਹੀਨਿਆਂ ਦੇ ਇਨਵੌਇਸਾਂ ਦੀ ਤੁਲਨਾ ਕਰੋ।|pichle tin mahinean de invoicean di tulna karo.
pa|I|CBC ਦੀ ਕੀਮਤ ਅਤੇ ਰਿਪੋਰਟ ਦਾ ਸਮਾਂ ਕੀ ਹੈ?|CBC di keemat te report da samaan ki hai?
pa|J|ਰੱਦ ਕੀਤੇ ਸੈਂਪਲ ਦਿਖਾਓ।|radd kite sample dikhao.
pa|K|ਮੇਰੇ ਤਾਜ਼ਾ 10 ਬਿੱਲ ਦਿਖਾਓ।|mere taza 10 bill dikhao.
pa|L|ਇਸ ਮਹੀਨੇ ਮੇਰੀ ਕੁੱਲ ਬਿਲਿੰਗ ਕਿੰਨੀ ਹੈ?|is mahine meri kul billing kinni hai?
pa|M|ਇਕਰਾਰਨਾਮੇ ਦੇ ਵੇਰਵੇ ਦਿਖਾਓ।|ikrarname de vere dikhao.
pa|N|ਅਦਾਇਗੀ ਦੀ ਸਥਿਤੀ ਕੀ ਹੈ?|adaigi di sthiti ki hai?
ur|A|اس مہینے کتنے بل بنے؟|is mahine kitne bill bane?
ur|B|اس مہینے کتنی انوائسز بنیں؟|is mahine kitni invoices baneen?
ur|C|میری رپورٹس کی کیا حالت ہے؟|meri reports ki kya halat hai?
ur|D|کون سی رپورٹس باقی ہیں؟|kaun si reports baqi hain?
ur|E|کون سے آرڈر لیٹ ہو سکتے ہیں؟|kaun se order late ho sakte hain?
ur|F|اس مہینے کتنے فیصد رپورٹس TAT میں آئیں؟|is mahine kitne feesad reports TAT mein aayin?
ur|G|ہمارے سیمپل مسترد ہونے کی شرح کتنی ہے؟|hamare sample mustarad hone ki sharah kitni hai?
ur|H|پچھلے تین مہینوں کی انوائسز کا موازنہ کریں۔|pichle teen mahinon ki invoices ka muazna karen.
ur|I|CBC کی قیمت اور رپورٹ کا وقت کیا ہے؟|CBC ki qeemat aur report ka waqt kya hai?
ur|J|مسترد شدہ سیمپل دکھائیں۔|mustarad shuda sample dikhayen.
ur|K|میرے تازہ 10 بل دکھائیں۔|mere taza 10 bill dikhayen.
ur|L|اس مہینے میری کل بلنگ کتنی ہے؟|is mahine meri kul billing kitni hai?
ur|M|معاہدے کی تفصیلات دکھائیں۔|muahide ki tafseelat dikhayen.
ur|N|ادائیگی کی کیا حالت ہے؟|adaigi ki kya halat hai?
or|A|ଏହି ମାସରେ କେତୋଟି ବିଲ୍ ହୋଇଛି?|ehi masa re kete bill heichi?
or|B|ଏହି ମାସରେ କେତୋଟି ଇନଭଏସ୍ ହୋଇଛି?|ehi masa re kete invoice heichi?
or|C|ମୋ ରିପୋର୍ଟର ସ୍ଥିତି କ'ଣ?|mo reportara sthiti kana?
or|D|କେଉଁ ରିପୋର୍ଟ ବାକି ଅଛି?|keu report baki achhi?
or|E|କେଉଁ ଅର୍ଡର ବିଳମ୍ବ ହେବାର ସମ୍ଭାବନା ଅଛି?|keu order bilamba hebara sambhabana achhi?
or|F|ଏହି ମାସରେ କେତେ ପ୍ରତିଶତ ରିପୋର୍ଟ TAT ଭିତରେ ଆସିଛି?|ehi masa re kete pratisata report TAT bhitare asichhi?
or|G|ଆମର ସାମ୍ପଲ୍ ପ୍ରତ୍ୟାଖ୍ୟାନ ପ୍ରତିଶତ କେତେ?|amara sample pratyakhyana pratisata kete?
or|H|ଗତ ତିନି ମାସର ଇନଭଏସ୍ ତୁଳନା କରନ୍ତୁ।|gata tini masara invoice tulana karantu.
or|I|CBC ର ମୂଲ୍ୟ ଓ ରିପୋର୍ଟ ସମୟ କେତେ?|CBC ra mulya o report samaya kete?
or|J|ପ୍ରତ୍ୟାଖ୍ୟାତ ସାମ୍ପଲ୍ ଦେଖାନ୍ତୁ।|pratyakhyata sample dekhantu.
or|K|ମୋର ସାମ୍ପ୍ରତିକ 10 ବିଲ୍ ଦେଖାନ୍ତୁ।|mora samprataka 10 bill dekhantu.
or|L|ଏହି ମାସରେ ମୋର ମୋଟ ବିଲିଂ କେତେ?|ehi masa re mora mota billing kete?
or|M|ଚୁକ୍ତିର ବିବରଣୀ ଦେଖାନ୍ତୁ।|chuktira bibarani dekhantu.
or|N|ପେମେଣ୍ଟ ସ୍ଥିତି କ'ଣ?|payment sthiti kana?"""
RANGE = {"ta": (0x0B80, 0x0BFF), "kn": (0x0C80, 0x0CFF), "ml": (0x0D00, 0x0D7F), "mr": (0x0900, 0x097F), "bn": (0x0980, 0x09FF), "gu": (0x0A80, 0x0AFF), "pa": (0x0A00, 0x0A7F), "ur": (0x0600, 0x06FF), "or": (0x0B00, 0x0B7F)}
ALLR = list(RANGE.values()) + [(0x0C00, 0x0C7F)]
def script_ok(code, ans):
    lo, hi = RANGE[code]; sent = ans.split(" | ")[0].replace("\u0964", "").replace("\u0965", "")
    mine = sum(1 for c in sent if lo <= ord(c) <= hi); other = sum(1 for c in sent if any(l <= ord(c) <= h for l, h in ALLR) and not (lo <= ord(c) <= hi))
    if code in ("mr", "ur"): other -= sum(1 for c in sent if 0x0900 <= ord(c) <= 0x097F)
    return mine >= 2 and other <= max(1, mine // 10)
def script_not_wrong(code, ans):
    lo, hi = RANGE[code]; sent = ans.split(" | ")[0].replace("\u0964", "").replace("\u0965", "")
    other = sum(1 for c in sent if any(l <= ord(c) <= h for l, h in ALLR) and not (lo <= ord(c) <= hi))
    if code in ("mr", "ur"): other -= sum(1 for c in sent if 0x0900 <= ord(c) <= 0x097F)
    return other <= 1
def nums(t): return set(x for x in re.findall(r"\d[\d.]*", t) if len(x.strip(".")) >= 2)
truth = {}
for k, q in EN.items():
    s, r = ask(tok, q); truth[k] = (r.get("intent"), nums(flat(r)), flat(r)[:120]); print("EN   %-18s intent=%s numbers=%d" % (NAME[k], truth[k][0], len(truth[k][1])), flush=True)
bank = []
for ln in DATA.splitlines():
    c, k, n, r = ln.split("|"); bank.append((c, k, "native", n)); bank.append((c, k, "english-letters", r))
import os
if os.path.exists("lang9b_result.csv"):
    try:
        _f = {r["question"] for r in csv.DictReader(open("lang9b_result.csv", encoding="utf-8-sig")) if r["verdict"] == "FAIL"}
        if _f: bank = [b for b in bank if b[3] in _f]; print("RETRY ONLY the %d earlier failures" % len(bank), flush=True)
    except Exception as _e: print("retry filter off:", _e)
if a.langs:
    keep = set(x.strip() for x in a.langs.split(",")); bank = [b for b in bank if b[0] in keep]
OUT = open("lang9b_retry.csv", "w", encoding="utf-8-sig", newline=""); W = csv.writer(OUT); W.writerow(["lang", "kind", "topic", "question", "verdict", "why", "answer"])
good = []; bad = []; per = {}
for code, k, kind, q in bank:
    s, r = ask(tok, q); ans = flat(r); ti, tn, _ = truth[k]; why = []
    if s != 200: why.append("http %s" % s)
    if r.get("intent") != ti: why.append("intent %s (English gives %s)" % (r.get("intent"), ti))
    if tn and len(tn & nums(ans)) < max(1, len(tn) // 2): why.append("numbers differ")
    if kind == "native" and not script_ok(code, ans): why.append("reply not in the user's language")
    if kind != "native" and not script_not_wrong(code, ans): why.append("reply in a different Indian language")
    ok = not why; per.setdefault((code, kind), [0, 0]); per[(code, kind)][1] += 1; per[(code, kind)][0] += ok
    (good if ok else bad).append((code, kind, k, q, "; ".join(why)))
    W.writerow([code, kind, NAME[k], q, "PASS" if ok else "FAIL", "; ".join(why), ans[:300]]); OUT.flush()
    print("%-4s %-3s %-15s %-16s %s%s" % ("PASS" if ok else "FAIL", code, kind, NAME[k], q, "" if ok else "\n        -> " + "; ".join(why) + " | " + ans[:110]), flush=True)
names = {"ta": "TAMIL", "kn": "KANNADA", "ml": "MALAYALAM", "mr": "MARATHI", "bn": "BENGALI", "gu": "GUJARATI", "pa": "PUNJABI", "ur": "URDU", "or": "ODIA"}
with open("sahasra_CONFIRMED_retryB.txt", "w", encoding="utf-8") as f:
    f.write("SAHASRA AI AGENT - CONFIRMED QUESTIONS, SET B (live server). Only questions whose answer matched the English answer and came back in the user's language.\n\n")
    for c in names:
        g = [x for x in good if x[0] == c]
        f.write("=== %s (%d confirmed) ===\n" % (names[c], len(g)))
        for kind, t in (("native", "native script"), ("english-letters", "English letters")):
            f.write("  -- %s --\n" % t)
            for x in g:
                if x[1] == kind: f.write("     %-18s %s\n" % (NAME[x[2]], x[3]))
        f.write("\n")
print("\nCONFIRMED %d of %d" % (len(good), len(bank)))
for key in sorted(per): print("  %s %-16s %d/%d" % (key[0], key[1], per[key][0], per[key][1]))
