"""Translation memory: export for a native speaker to review, or clear a language.
   python tm_export.py              -> lang_tm_review.csv  (language, English wording with {N1} number slots, translation)
   python tm_export.py --clear ta   -> forget Tamil (re-translated on next use)   |  --clear all
Read-only on the lab data; touches only lang_tm.db."""
import csv, os, sqlite3, sys
p = os.getenv("SAHASRA_LANG_TM_DB") or os.path.join(os.getcwd(), "lang_tm.db")
if not os.path.exists(p):
    print("no lang_tm.db yet (nothing translated since patch 132)"); sys.exit(0)
c = sqlite3.connect(p)
if "--clear" in sys.argv:
    k = sys.argv[sys.argv.index("--clear") + 1]
    n = c.execute("DELETE FROM tm" if k == "all" else "DELETE FROM tm WHERE lang=?", () if k == "all" else (k,)).rowcount
    c.commit(); print("cleared", n, "entries"); sys.exit(0)
rows = c.execute("SELECT lang, roman, src, out, created FROM tm ORDER BY lang, roman, src").fetchall()
with open("lang_tm_review.csv", "w", encoding="utf-8-sig", newline="") as fh:
    w = csv.writer(fh); w.writerow(["language", "english_letters", "english_with_slots", "translation", "created"]); w.writerows(rows)
print(len(rows), "entries -> lang_tm_review.csv")
