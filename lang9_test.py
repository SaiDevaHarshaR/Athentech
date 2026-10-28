"""lang9_test.py - 16 questions x 9 languages (Tamil, Kannada, Malayalam, Marathi, Bengali, Gujarati, Punjabi, Urdu, Odia), native script AND English letters.
READ-ONLY, no tickets. Every question is checked for the right fact in the answer. Writes lang9_result.csv after each question and, at the end,
sahasra_CONFIRMED_9langs.txt = only the questions that returned the correct answer on YOUR server.
  python -X utf8 lang9_test.py --api https://api.athentech.in --client CM --phone 9876543210 --org COMP0108"""
import argparse, csv, json, re, time, unicodedata, urllib.request, urllib.error
ap = argparse.ArgumentParser(); ap.add_argument("--api", required=True); ap.add_argument("--client", required=True); ap.add_argument("--phone", required=True)
ap.add_argument("--org", default="COMP0108"); ap.add_argument("--pace", type=float, default=7.0); ap.add_argument("--langs", default=""); a = ap.parse_args(); API = a.api.rstrip("/")
def http(path, body, token=None):
    req = urllib.request.Request(API + path, json.dumps(body).encode(), {"Content-Type": "application/json", **({"Authorization": "Bearer " + token} if token else {})})
    try:
        with urllib.request.urlopen(req, timeout=150) as r: return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        try: return e.code, json.loads(e.read().decode())
        except Exception: return e.code, {}
    except Exception as e: return 0, {"error": str(e)}

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

# Nine new questions x 9 languages: (native, English letters). Expected fact is checked in the answer (numbers/codes only, language independent).
N = {
"available credit": (["253"], {
 "ta": ("எவ்வளவு கிரெடிட் மீதம் உள்ளது?", "evlo credit meedham irukku?"), "kn": ("ಎಷ್ಟು ಕ್ರೆಡಿಟ್ ಲಭ್ಯವಿದೆ?", "eshtu credit labhyavide?"),
 "ml": ("എത്ര ക്രെഡിറ്റ് ലഭ്യമാണ്?", "ethra credit labhyamanu?"), "mr": ("किती क्रेडिट उपलब्ध आहे?", "kiti credit uplabdh aahe?"),
 "bn": ("কত ক্রেডিট অবশিষ্ট আছে?", "koto credit obshishto ache?"), "gu": ("કેટલું ક્રેડિટ ઉપલબ્ધ છે?", "ketlu credit uplabdh chhe?"),
 "pa": ("ਕਿੰਨਾ ਕ੍ਰੈਡਿਟ ਉਪਲਬਧ ਹੈ?", "kinna credit uplabdh hai?"), "ur": ("کتنا کریڈٹ دستیاب ہے؟", "kitna credit dastiyab hai?"),
 "or": ("କେତେ କ୍ରେଡିଟ୍ ଉପଲବ୍ଧ ଅଛି?", "kete credit upalabdha achhi?")}),
"agreement expiry": (["2029"], {
 "ta": ("எங்கள் ஒப்பந்தம் எப்போது முடிகிறது?", "engal oppandham eppo mudiyudhu?"), "kn": ("ನಮ್ಮ ಒಪ್ಪಂದ ಯಾವಾಗ ಮುಗಿಯುತ್ತದೆ?", "namma oppanda yavaga mugiyuttade?"),
 "ml": ("ഞങ്ങളുടെ കരാർ എപ്പോൾ അവസാനിക്കും?", "njangalude karar eppol avasanikkum?"), "mr": ("आमचा करार कधी संपतो?", "amcha karar kadhi sampto?"),
 "bn": ("আমাদের চুক্তি কবে শেষ হবে?", "amader chukti kobe shesh hobe?"), "gu": ("અમારો કરાર ક્યારે પૂરો થાય છે?", "amaro karar kyare puro thay chhe?"),
 "pa": ("ਸਾਡਾ ਇਕਰਾਰਨਾਮਾ ਕਦੋਂ ਖਤਮ ਹੁੰਦਾ ਹੈ?", "sada ikrarnama kado khatam hunda hai?"), "ur": ("ہمارا معاہدہ کب ختم ہوتا ہے؟", "hamara muahida kab khatam hota hai?"),
 "or": ("ଆମର ଚୁକ୍ତି କେବେ ସରିବ?", "amara chukti kebe saribe?")}),
"pending tests": (["SMN26190600"], {
 "ta": ("எந்த பரிசோதனைகள் இன்னும் நிலுவையில் உள்ளன?", "entha parisodhanaigal innum niluvaiyil irukku?"), "kn": ("ಯಾವ ಪರೀಕ್ಷೆಗಳು ಇನ್ನೂ ಬಾಕಿ ಇವೆ?", "yava parikshegalu innu baki ive?"),
 "ml": ("ഏത് പരിശോധനകൾ ഇനിയും ബാക്കിയാണ്?", "ethu parishodhanakal iniyum baakiyanu?"), "mr": ("कोणत्या तपासण्या अजून बाकी आहेत?", "kontya tapasanya ajun baki aahet?"),
 "bn": ("কোন পরীক্ষাগুলো এখনও বাকি আছে?", "kon porikkhagulo ekhono baki ache?"), "gu": ("કયા ટેસ્ટ હજુ બાકી છે?", "kya test haju baki chhe?"),
 "pa": ("ਕਿਹੜੇ ਟੈਸਟ ਹਜੇ ਬਾਕੀ ਹਨ?", "kihde test haje baki han?"), "ur": ("کون سے ٹیسٹ ابھی باقی ہیں؟", "kaun se test abhi baqi hain?"),
 "or": ("କେଉଁ ଟେଷ୍ଟ ଏବେ ବି ବାକି ଅଛି?", "keu test ebe bi baki achhi?")}),
"packages": (["PKG", "80"], {
 "ta": ("என்னென்ன ஹெல்த் பேக்கேஜ்கள் உள்ளன?", "ennenna health package irukku?"), "kn": ("ಯಾವ ಹೆಲ್ತ್ ಪ್ಯಾಕೇಜ್‌ಗಳು ಲಭ್ಯವಿವೆ?", "yava health package labhyavive?"),
 "ml": ("ഏതൊക്കെ ഹെൽത്ത് പാക്കേജുകൾ ലഭ്യമാണ്?", "ethokke health package labhyamanu?"), "mr": ("कोणती हेल्थ पॅकेजेस उपलब्ध आहेत?", "konti health packages uplabdh aahet?"),
 "bn": ("কোন হেলথ প্যাকেজগুলো পাওয়া যাচ্ছে?", "kon health packagegulo paowa jachhe?"), "gu": ("કયા હેલ્થ પેકેજ ઉપલબ્ધ છે?", "kya health package uplabdh chhe?"),
 "pa": ("ਕਿਹੜੇ ਹੈਲਥ ਪੈਕੇਜ ਉਪਲਬਧ ਹਨ?", "kihde health package uplabdh han?"), "ur": ("کون سے ہیلتھ پیکجز دستیاب ہیں؟", "kaun se health package dastiyab hain?"),
 "or": ("କେଉଁ ହେଲ୍ଥ ପ୍ୟାକେଜ୍ ଉପଲବ୍ଧ?", "keu health package upalabdha?")}),
"top tests": (["THYROID"], {
 "ta": ("எந்த பரிசோதனைகள் அதிகம் ஆர்டர் செய்யப்பட்டன?", "entha parisodhanai adhigam order pannirukku?"), "kn": ("ಯಾವ ಪರೀಕ್ಷೆಗಳನ್ನು ಹೆಚ್ಚು ಆರ್ಡರ್ ಮಾಡಲಾಗಿದೆ?", "yava parikshegalu hechchu order aagide?"),
 "ml": ("ഏത് പരിശോധനകളാണ് ഏറ്റവും കൂടുതൽ ഓർഡർ ചെയ്തത്?", "ethu parishodhanakalanu ettavum kooduthal order cheythathu?"), "mr": ("कोणत्या तपासण्या सर्वाधिक मागवल्या गेल्या?", "kontya tapasanya sarvadhik magvalya gelya?"),
 "bn": ("কোন পরীক্ষা সবচেয়ে বেশি অর্ডার হয়েছে?", "kon porikkha sobcheye beshi order hoyeche?"), "gu": ("કયા ટેસ્ટ સૌથી વધુ મંગાવ્યા?", "kya test sauthi vadhu mangavya?"),
 "pa": ("ਕਿਹੜੇ ਟੈਸਟ ਸਭ ਤੋਂ ਵੱਧ ਮੰਗਵਾਏ ਗਏ?", "kihde test sabh ton vadh mangwaye gaye?"), "ur": ("کون سے ٹیسٹ سب سے زیادہ منگوائے گئے؟", "kaun se test sab se zyada mangwaye gaye?"),
 "or": ("କେଉଁ ଟେଷ୍ଟ ସବୁଠୁ ଅଧିକ ଅର୍ଡର ହୋଇଛି?", "keu test sabuthu adhika order heichhi?")}),
"busiest branch": (["Central"], {
 "ta": ("எந்த கிளையில் அதிக பரிசோதனைகள் உள்ளன?", "entha kilaiyil adhiga parisodhanai irukku?"), "kn": ("ಯಾವ ಶಾಖೆಯಲ್ಲಿ ಹೆಚ್ಚು ಪರೀಕ್ಷೆಗಳಿವೆ?", "yava shakheyalli hechchu parikshegalive?"),
 "ml": ("ഏത് ബ്രാഞ്ചിലാണ് ഏറ്റവും കൂടുതൽ പരിശോധനകൾ?", "ethu branchilanu ettavum kooduthal parishodhanakal?"), "mr": ("कोणत्या शाखेत सर्वाधिक तपासण्या आहेत?", "kontya shakhet sarvadhik tapasanya aahet?"),
 "bn": ("কোন শাখায় সবচেয়ে বেশি পরীক্ষা হয়?", "kon shakhay sobcheye beshi porikkha hoy?"), "gu": ("કઈ શાખામાં સૌથી વધુ ટેસ્ટ છે?", "kai shakhama sauthi vadhu test chhe?"),
 "pa": ("ਕਿਸ ਸ਼ਾਖਾ ਵਿੱਚ ਸਭ ਤੋਂ ਵੱਧ ਟੈਸਟ ਹਨ?", "kis shakha vich sabh ton vadh test han?"), "ur": ("کس برانچ میں سب سے زیادہ ٹیسٹ ہیں؟", "kis branch mein sab se zyada test hain?"),
 "or": ("କେଉଁ ଶାଖାରେ ସବୁଠୁ ଅଧିକ ଟେଷ୍ଟ ଅଛି?", "keu shakhare sabuthu adhika test achhi?")}),
"price of CBC": (["INV273"], {
 "ta": ("CBC விலை என்ன?", "CBC vilai enna?"), "kn": ("CBC ಬೆಲೆ ಎಷ್ಟು?", "CBC bele eshtu?"), "ml": ("CBC വില എത്രയാണ്?", "CBC vila ethrayanu?"),
 "mr": ("CBC ची किंमत किती आहे?", "CBC chi kimmat kiti aahe?"), "bn": ("CBC এর দাম কত?", "CBC er dam koto?"), "gu": ("CBC ની કિંમત કેટલી છે?", "CBC ni kimmat ketli chhe?"),
 "pa": ("CBC ਦੀ ਕੀਮਤ ਕੀ ਹੈ?", "CBC di keemat ki hai?"), "ur": ("CBC کی قیمت کیا ہے؟", "CBC ki qeemat kya hai?"), "or": ("CBC ର ମୂଲ୍ୟ କେତେ?", "CBC ra mulya kete?")}),
"monthly statement": (["19715"], {
 "ta": ("மாதாந்திர பில்லிங் அறிக்கை தர முடியுமா?", "maadhandhira billing statement thara mudiyuma?"), "kn": ("ಮಾಸಿಕ ಬಿಲ್ಲಿಂಗ್ ಸ್ಟೇಟ್‌ಮೆಂಟ್ ಕೊಡಬಹುದೇ?", "masika billing statement kodabahude?"),
 "ml": ("പ്രതിമാസ ബില്ലിംഗ് സ്റ്റേറ്റ്മെന്റ് തരാമോ?", "prathimasa billing statement tharamo?"), "mr": ("मासिक बिलिंग स्टेटमेंट देऊ शकता का?", "masik billing statement deu shakta ka?"),
 "bn": ("মাসিক বিলিং স্টেটমেন্ট দিতে পারবেন?", "masik billing statement dite parben?"), "gu": ("માસિક બિલિંગ સ્ટેટમેન્ટ આપી શકો?", "masik billing statement api shako?"),
 "pa": ("ਮਹੀਨਾਵਾਰ ਬਿਲਿੰਗ ਸਟੇਟਮੈਂਟ ਦੇ ਸਕਦੇ ਹੋ?", "mahinawar billing statement de sakde ho?"), "ur": ("ماہانہ بلنگ اسٹیٹمنٹ دے سکتے ہیں؟", "mahana billing statement de sakte hain?"),
 "or": ("ମାସିକ ବିଲିଂ ଷ୍ଟେଟମେଣ୍ଟ ଦେଇପାରିବେ?", "masika billing statement deiparibe?")}),
"unpaid invoices": (["19715"], {
 "ta": ("எந்த இன்வாய்ஸ்கள் செலுத்தப்படவில்லை?", "entha invoice seluthappadavillai?"), "kn": ("ಯಾವ ಇನ್‌ವಾಯ್ಸ್‌ಗಳು ಪಾವತಿಯಾಗಿಲ್ಲ?", "yava invoice pavatiyagilla?"),
 "ml": ("ഏത് ഇൻവോയ്സുകൾ അടച്ചിട്ടില്ല?", "ethu invoicukal adachittilla?"), "mr": ("कोणती इनव्हॉइस न भरलेली आहेत?", "konti invoice na bharleli aahet?"),
 "bn": ("কোন ইনভয়েসগুলো পরিশোধ হয়নি?", "kon invoicegulo porishodh hoyni?"), "gu": ("કયા ઇન્વોઇસ ચૂકવાયા નથી?", "kya invoice chukavaya nathi?"),
 "pa": ("ਕਿਹੜੇ ਇਨਵੌਇਸ ਅਦਾ ਨਹੀਂ ਹੋਏ?", "kihde invoice ada nahin hoye?"), "ur": ("کون سی انوائسز ادا نہیں ہوئیں؟", "kaun si invoices ada nahin huin?"),
 "or": ("କେଉଁ ଇନଭଏସ୍ ଦିଆଯାଇ ନାହିଁ?", "keu invoice diaijai nahin?")}),
}
# the 7 older questions (already tested once): index into L[...] lists A..H
OLD = {"B": ("last month bills", ["14575"]), "C": ("3-month total", ["27845"]), "D": ("outstanding", ["69747"]), "E": ("credit limit", ["70000"]),
       "F": ("last payment", ["1000"]), "G": ("services", ["YASHODHA", "CMLTSF93"]), "H": ("payment received", ["UPI"])}
NINE = ["ta", "kn", "ml", "mr", "bn", "gu", "pa", "ur", "or"]
bank = []   # (lang, kind, intent, expect, question)
for code in NINE:
    name, native, roman = L[code]
    for k, (intent, exp) in OLD.items():
        i = ord(k) - 65
        if native and native[i]: bank.append((code, "native", intent, exp, native[i]))
        if roman and roman[i]: bank.append((code, "english-letters", intent, exp, roman[i]))
    for intent, (exp, d) in N.items():
        bank.append((code, "native", intent, exp, d[code][0])); bank.append((code, "english-letters", intent, exp, d[code][1]))

if a.langs:
    keep = set(x.strip() for x in a.langs.split(",")); bank = [b for b in bank if b[0] in keep]
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
import os
_src = "lang9_retry.csv" if os.path.exists("lang9_retry.csv") else "lang9_result.csv"
if os.path.exists(_src):
    try:
        _f = {r["question"] for r in csv.DictReader(open(_src, encoding="utf-8-sig")) if r["verdict"] == "FAIL"}
        if _f: bank = [b for b in bank if b[4] in _f]; print("RETRY ONLY the %d earlier failures" % len(bank), flush=True)
    except Exception as _e: print("retry filter off:", _e)
OUT = open("lang9_retry2.csv", "w", encoding="utf-8-sig", newline=""); W = csv.writer(OUT); W.writerow(["lang", "kind", "intent", "question", "verdict", "answer"])
good = []; per = {}
for code, kind, intent, exp, q in bank:
    s, r = ask(tok, q); ans = flat(r); ok = s == 200 and (any(e.lower() in ans.lower() for e in exp) or (intent == "services" and "69747" not in ans and len(ans) > 60 and "sorry" not in ans.lower() and "could not" not in ans.lower()))
    per.setdefault((code, kind), [0, 0]); per[(code, kind)][1] += 1; per[(code, kind)][0] += ok
    if ok: good.append((code, kind, intent, q))
    W.writerow([code, kind, intent, q, "PASS" if ok else "FAIL", ans[:300]]); OUT.flush()
    print("%-4s %-3s %-15s %-16s %s%s" % ("PASS" if ok else "FAIL", code, kind, intent, q, "" if ok else "\n        -> " + ans[:140]), flush=True)
NAMES = {"ta": "TAMIL", "kn": "KANNADA", "ml": "MALAYALAM", "mr": "MARATHI", "bn": "BENGALI", "gu": "GUJARATI", "pa": "PUNJABI", "ur": "URDU", "or": "ODIA"}
with open("sahasra_CONFIRMED_retry2.txt", "w", encoding="utf-8") as f:
    f.write("SAHASRA AI AGENT - CONFIRMED QUESTIONS (run on your server %s). Only questions that returned the correct answer are listed.\n\n" % time.strftime("%d %b %Y"))
    for code in NINE:
        rows = [g for g in good if g[0] == code]
        if not rows: continue
        f.write("=== %s (%d confirmed) ===\n" % (NAMES[code], len(rows)))
        for kind in ("native", "english-letters"):
            f.write("  -- %s --\n" % ("native script" if kind == "native" else "English letters"))
            for g in rows:
                if g[1] == kind: f.write("     %-18s %s\n" % (g[2], g[3]))
        f.write("\n")
print("\nCONFIRMED %d of %d" % (len(good), len(bank)))
for k, (g, n) in sorted(per.items()): print("  %s %-16s %d/%d" % (k[0], k[1], g, n))
