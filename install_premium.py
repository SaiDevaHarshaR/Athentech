"""Run from the app folder:  python install_premium.py
Checks the files are there, adds the 2 tags to widget_files/index.html (cache-busted), and tests the live URLs."""
import os, re, shutil, sys, time, urllib.request
D = "widget_files"; P = D + "/index.html"; v = str(int(time.time()))
need = ["premium.js", "premium.css"]
missing = [f for f in need if not os.path.exists(f"{D}/{f}")]
if missing: print("MISSING in widget_files:", missing, "- copy them in, then rerun."); sys.exit(1)
s = open(P, encoding="utf-8").read()
s2 = re.sub(r'\n?<link rel="stylesheet" href="premium\.css[^"]*">', "", s)
s2 = re.sub(r'<script src="premium\.js[^"]*" defer></script>\n?', "", s2)
a = '<link rel="stylesheet" href="theme.css">'
if s2.count(a) != 1 or s2.count("</body>") != 1: print("index.html anchors not found. Send me the <head> lines of widget_files/index.html."); sys.exit(1)
s2 = s2.replace(a, a + f'\n<link rel="stylesheet" href="premium.css?v={v}">', 1).replace("</body>", f'<script src="premium.js?v={v}" defer></script>\n</body>', 1)
if s2 != s:
    shutil.copy2(P, P + ".bak-" + v); open(P, "w", encoding="utf-8").write(s2)
print("index.html: tags present (v=%s)" % v)
for base in ("https://api.athentech.in/widget/", "https://sahasraaiagent.athentech.in/", "https://sahasraaiagent.athentech.in/widget/"):
    for f in need:
        try:
            r = urllib.request.urlopen(urllib.request.Request(base + f + "?v=" + v, headers={"User-Agent": "chk"}), timeout=10)
            print("OK  ", r.status, base + f, r.headers.get("Content-Type"))
        except Exception as e: print("FAIL", base + f, e)
