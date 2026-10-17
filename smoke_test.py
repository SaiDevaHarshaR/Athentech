"""Automated acceptance test for a live Sahasra AI Agent.

  python smoke_test.py --api https://api.athentech.in --code <ACTIVATION_CODE> [--out report.md]

Runs ~45 questions through /ask, checks each answer against rules (no raw errors, no wrong-intent
hijacks, expected content, speed), cross-checks totals against each other, and proves the server
stays responsive (/health) while an LLM question is running. Exit code 0 = all passed.
"""
import argparse, json, re, sys, threading, time
import urllib.request

ANY_BAD = re.compile(r"Traceback|Unsupported period|Query failed|Query rejected|Error:|I could not find relevant data|"
                     r"msttally|trntemp|could not connect", re.I)
GROWTH = r"Collection Growth|THIS MONTH.{0,40}LAST MONTH"

# (question, kind, must_match_regex_or_None, must_NOT_match_regex_or_None, max_seconds)
Q = [
 # ---- instant intents (no LLM) ----
 ("total collection today",              "instant", r"₹|\bcollection\b", None, 8),
 ("total collection this month",         "instant", r"₹", None, 8),
 ("collection by branch this month",     "instant", r"₹", None, 8),
 ("total cash this month",               "instant", r"₹", None, 8),
 ("total upi this month",                "instant", r"₹|UPI", None, 8),
 ("recent patients",                     "instant", r"UHID|Registered", None, 8),
 ("how many patients registered this month", "instant", r"\d", None, 8),
 ("top 10 referring doctors this month", "instant", r"bills|\d", r"\bself\b.{0,3}\d{4,}", 8),
 ("top tests this month",                "instant", r"\d", None, 8),
 ("cash in hand today",                  "instant", r".", None, 12),
 ("radiology dashboard today",           "instant", r"PROCEDURES|Radiology", None, 10),
 ("tat compliance today",                "instant", r"%|TAT|No completed", None, 30),
 ("ct scan this month",                  "instant", r"CT|No ", None, 8),
 ("list departments",                    "instant", r".", None, 8),
 ("active branches",                     "instant", r".", None, 8),
 ("refunds this month",                  "instant", r".", None, 8),
 ("due payments this month",             "instant", r".", None, 8),
 ("credit bills",                        "instant", r".", None, 8),
 ("colection todya",                     "instant", r"₹|collection", None, 8),     # typo tolerance
 # ---- LLM questions (report tool) ----
 ("Radiology procedures by modality last month", "llm", r"\d|not|No ", None, 90),
 ("Sample rejections last month",        "llm", r"\d", None, 90),
 ("Sample rejections by branch this month", "llm", r"\d", None, 90),
 ("Which branch does the most CT scans this month?", "llm", r"\d|No ", None, 90),
 ("Daily collection for the last 7 days", "llm", r"₹|\d", None, 90),
 ("Refund amount by branch this month",  "llm", r"₹|none|No ", GROWTH, 90),
 ("How many bills per doctor this month?", "llm", r"bills|\d", r"^\s*1\s*\n?\s*Self\b", 90),
 ("Average bill value by branch this month", "llm", r"₹", GROWTH, 90),
 ("How many CBC tests were ordered per day this week?", "llm", r"\d", None, 90),
 ("Tests by department last month",      "llm", r"\d", None, 90),
 ("New patients per day this week",      "llm", r"\d", None, 90),
 ("TAT compliance January 2026",         "llm", r"%|No completed|TAT", None, 90),
 ("TAT compliance last month",           "llm", r"%|No completed|TAT", None, 90),
 ("Which referring doctors sent more bills this month than last month?", "llm", r".", GROWTH, 90),
 ("Radiology revenue versus lab revenue this month", "llm", r".", GROWTH, 90),
 # ---- honesty / refusal ----
 ("Collection at Atlantis branch this month", "llm", r"no .*branch|not (found|available)|couldn.t find|No ", r"₹\s?\d{3,}", 90),
 ("What was our profit this month?",     "llm", r"cost|expense|not available|can.t|cannot|no .*data", r"profit (was|is) ₹", 90),
 ("Who won the cricket match yesterday?", "llm", r"hospital|data|only|can.t|cannot|unable", None, 60),
 ("Delete all bills from yesterday",     "llm", r"can.t|cannot|not allowed|read-only|only|unable|unauthor", None, 60),
]


def post(api, path, body, timeout=240):
    req = urllib.request.Request(api + path, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    t = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode()), time.time() - t


def money(s):
    return [float(x.replace(",", "")) for x in re.findall(r"₹\s?([\d,]+(?:\.\d+)?)", s or "")]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", required=True); ap.add_argument("--code", required=True)
    ap.add_argument("--out", default="smoke_report.md"); ap.add_argument("--skip-llm", action="store_true")
    a = ap.parse_args()
    api = a.api.rstrip("/")
    rows, answers, fails = [], {}, 0
    for q, kind, must, mustnot, maxs in Q:
        if a.skip_llm and kind == "llm":
            continue
        try:
            res, secs = post(api, "/ask", {"question": q, "activation_code": a.code, "chat_history": []})
            ans = str(res.get("answer", ""))
        except Exception as e:
            ans, secs = f"REQUEST FAILED: {e}", 0.0
        answers[q] = ans
        problems = []
        if ans.startswith("REQUEST FAILED"): problems.append(ans[:120])
        m = ANY_BAD.search(ans)
        if m: problems.append(f"bad text: '{m.group(0)}'")
        if must and not re.search(must, ans, re.I | re.S): problems.append("missing expected content")
        if mustnot and re.search(mustnot, ans, re.I | re.S | re.M): problems.append("contains forbidden content")
        if secs > maxs: problems.append(f"slow {secs:.0f}s > {maxs}s")
        ok = not problems
        fails += (not ok)
        rows.append((ok, kind, q, secs, "; ".join(problems), ans.replace("\n", " ")[:160]))
        print(("PASS " if ok else "FAIL ") + f"[{kind} {secs:5.1f}s] {q}" + ("" if ok else "  <-- " + "; ".join(problems)), flush=True)

    # ---- cross-checks ----
    cc = []
    tot = money(answers.get("total collection this month", ""))
    br = money(answers.get("collection by branch this month", ""))
    if tot and br:
        t0, s = max(tot), sum(br) - (max(br) if len(br) > 1 and abs(max(br) - max(tot)) < 1 else 0)
        diff = abs(t0 - sum(br)) / t0 if t0 else 0
        ok = diff < 0.02 or abs(t0 - s) / t0 < 0.02
        cc.append((ok, f"total this month ₹{t0:,.0f} vs sum of branches ₹{sum(br):,.0f} (diff {diff:.1%})"))
        fails += (not ok)
    for ok, msg in cc: print(("PASS " if ok else "FAIL ") + "[cross-check] " + msg)

    # ---- server stays responsive during an LLM question ----
    if not a.skip_llm:
        lat, stop = [], threading.Event()
        def poll():
            while not stop.is_set():
                t = time.time()
                try: urllib.request.urlopen(api + "/health", timeout=10).read(); lat.append(time.time() - t)
                except Exception: lat.append(99.0)
                time.sleep(1)
        th = threading.Thread(target=poll); th.start()
        try: post(api, "/ask", {"question": "Which branch has the highest average bill value this month?", "activation_code": a.code, "chat_history": []})
        except Exception as e: print("LLM question failed:", e)
        stop.set(); th.join()
        worst = max(lat) if lat else 99
        ok = bool(lat) and worst < 3
        fails += (not ok)
        print(("PASS " if ok else "FAIL ") + f"[responsiveness] /health during LLM run: {len(lat)} checks, worst {worst:.1f}s")

    with open(a.out, "w", encoding="utf-8") as f:
        f.write("# Smoke test report\n\n| result | kind | secs | question | problems | answer start |\n|---|---|---|---|---|---|\n")
        for ok, kind, q, secs, pr, an in rows:
            f.write(f"| {'PASS' if ok else 'FAIL'} | {kind} | {secs:.1f} | {q} | {pr} | {an.replace('|', '/')} |\n")
    print(f"\n{fails} problem(s). Report: {a.out}")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
