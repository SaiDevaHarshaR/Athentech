"""Runs EVERY question in sahasra_questions_te_hi.txt (English, Telugu, Hindi) against the live API, READ-ONLY.
Writes questions_result.csv and sahasra_questions_te_hi_VERIFIED.txt (only questions that passed in both languages)."""
import argparse, csv, json, re, time, unicodedata, urllib.request, urllib.error
ap = argparse.ArgumentParser(); ap.add_argument("--api", required=True); ap.add_argument("--client", required=True)
ap.add_argument("--phone", required=True); ap.add_argument("--org", default="COMP0108")
ap.add_argument("--from", dest="n0", type=int, default=1); ap.add_argument("--to", dest="n1", type=int, default=999); ap.add_argument("--langs", default="te,hi"); ap.add_argument("--file", default="sahasra_questions_te_hi.txt"); ap.add_argument("--pace", type=float, default=8.0)
a = ap.parse_args(); API = a.api.rstrip("/")
def http(path, body, token=None):
    req = urllib.request.Request(API + path, json.dumps(body).encode(), {"Content-Type": "application/json", **({"Authorization": "Bearer " + token} if token else {})})
    try:
        with urllib.request.urlopen(req, timeout=150) as r: return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        try: return e.code, json.loads(e.read().decode())
        except Exception: return e.code, {}
    except Exception as e: return 0, {"error": str(e)}
RNG = {"te": (0x0C00, 0x0C7F), "hi": (0x0900, 0x097F)}
def native(t, c):
    lo, hi = RNG[c]; L = [x for x in t if x.isalpha()]
    return bool(L) and sum(lo <= ord(x) <= hi for x in L) / len(L) > 0.2
def flat(j):
    t = str((j or {}).get("answer", "") or ""); tb = (j or {}).get("table") or {}
    if isinstance(tb, dict): t += " | " + " ; ".join(" / ".join(map(str, r)) for r in tb.get("rows", [])[:25])
    return re.sub(r"\s+", " ", t)
def nums(t):
    t = "".join(str(unicodedata.digit(c)) if c.isdigit() and not c.isascii() else c for c in t)
    return set(re.findall(r"\d+(?:\.\d+)?", re.sub(r"(?<=\d),(?=\d)", "", t)))
def ask(tok, q):
    for _ in range(4):
        s, r = http("/public/b2b/chat", {"client": a.client, "message": q, "period": "this_month", "chat_history": []}, tok)
        if s == 429: time.sleep(65); continue
        time.sleep(a.pace); return s, r
    return 429, {}
# parse
items, cur = [], None; sec = ""
for ln in open(a.file, encoding="utf-8"):
    ln = ln.rstrip("\n")
    m = re.match(r"=== (.*) ===", ln)
    if m: sec = m.group(1); continue
    m = re.match(r"(\d+)\.(?: \[T\])? (.*)", ln)
    if m: cur = {"n": m.group(1), "sec": sec, "en": m.group(2)}; items.append(cur); continue
    if cur and ln.strip().startswith("తెలుగు:"): cur["te"] = ln.split(":", 1)[1].strip()
    if cur and ln.strip().startswith("हिन्दी:"): cur["hi"] = ln.split(":", 1)[1].strip()
s, j = http("/public/b2b/test-register", {"client": a.client, "phone": a.phone, "org_code": a.org, "name": "QTest"})
if s != 200: raise SystemExit("test-register failed %s %s (is test-register switch ON?)" % (s, j))
s, j2 = http("/public/b2b/verify-otp", {"client": a.client, "phone": j["phone"], "code": j["test_code"]})
tok = j2.get("token") or j2.get("access_token")
if not tok: raise SystemExit("login failed")
BAD = re.compile(r"(?i)traceback|query failed|internal error|unsupported|couldn.t understand|not able to|cannot help|i don.t have|unable to")
rows, good = [], {}
OUT = open("questions_result.csv", "w", encoding="utf-8-sig", newline=""); W = csv.writer(OUT); W.writerow(["#", "section", "lang", "question", "verdict", "why", "answer"])
for it in [x for x in items if a.n0 <= int(x["n"]) <= a.n1]:
    s, r = ask(tok, it["en"]); ea = flat(r); en_ok = s == 200 and not BAD.search(ea); en_n = nums(ea)
    res = {"en": ("OK" if en_ok else "EN-WEAK")}
    for c in a.langs.split(","):
        s2, r2 = ask(tok, it[c]); ans = flat(r2); why = []
        if s2 != 200: why.append("HTTP %s" % s2)
        if BAD.search(ans): why.append("refusal/error text")
        a_only = re.sub(r"\s+", " ", str((r2 or {}).get("answer", "") or ""))
        lang = (r2 or {}).get("lang") or ""
        if s2 == 200 and not native(a_only, c) and lang != c: why.append("not in %s script (lang=%s) ANSWER: %s" % (c, lang, a_only[:120]))
        extra = nums(ans) - en_n if en_n else set()
        v = "FAIL" if why else ("REVIEW" if (not en_ok or extra) else "PASS")
        if extra and not why: why.append("numbers not in English ref: %s" % sorted(extra)[:4])
        res[c] = v; res[c + "_n"] = nums(ans.split(" | ")[0])
        rows.append([it["n"], it["sec"], c, it[c], v, "; ".join(why), ans[:300]]); W.writerow(rows[-1]); OUT.flush()
        print("%s %-3s %-6s %s  %s\n     -> %s" % (it["n"], c, v, it[c], "; ".join(why), ans[:260]), flush=True)
        with open("questions_result.csv", "w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f); w.writerow(["#", "section", "lang", "question", "verdict", "why", "answer"]); w.writerows(rows)
    if res.get("te") == "PASS" and res.get("hi") == "PASS" and res["te_n"] != res["hi_n"]:
        res["te"] = res["hi"] = "REVIEW"; print("%s te/hi DISAGREE %s vs %s" % (it["n"], sorted(res["te_n"])[:4], sorted(res["hi_n"])[:4]), flush=True)
    good[it["n"]] = (it, res)
OUT.close()
with open("sahasra_questions_te_hi_VERIFIED.txt", "w", encoding="utf-8") as f:
    f.write("VERIFIED questions (PASS in both Telugu and Hindi)\n\n")
    for n, (it, res) in good.items():
        if res.get("te") == "PASS" and res.get("hi") == "PASS":
            f.write("%s. %s\n   తెలుగు: %s\n   हिन्दी: %s\n\n" % (n, it["en"], it["te"], it["hi"]))
p = sum(1 for r in rows if r[4] == "PASS"); fl = sum(1 for r in rows if r[4] == "FAIL")
print("\nPASS %d  FAIL %d  REVIEW %d  of %d" % (p, fl, len(rows) - p - fl, len(rows)))
