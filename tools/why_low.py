"""Why are answers marked low confidence?   python tools\\why_low.py [days] [client]
Counts the reasons stored with each low-confidence answer, by day, plus the most affected questions. Read-only."""
import collections
import json
import os
import sqlite3
import sys

days = int(sys.argv[1]) if len(sys.argv) > 1 else 3
client = sys.argv[2] if len(sys.argv) > 2 else None
db = os.environ.get("SAHASRA_ANSWER_DB") or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs", "answer_review.db")
c = sqlite3.connect(db)
w = "ts > datetime('now', ?)" + (" AND client=?" if client else "")
args = ("-%d day" % days,) + ((client,) if client else ())
tot = c.execute("SELECT COUNT(*), SUM(CASE WHEN ok=0 THEN 1 ELSE 0 END) FROM answer_log WHERE " + w, args).fetchone()
print("answers: %s   low confidence: %s" % tot)
print("\nBy day (answers / low):")
for d, n, lo in c.execute("SELECT substr(ts,1,10), COUNT(*), SUM(CASE WHEN ok=0 THEN 1 ELSE 0 END) FROM answer_log WHERE " + w + " GROUP BY 1 ORDER BY 1", args):
    print("  %s  %4d / %4d" % (d, n, lo or 0))
cnt, bysrc = collections.Counter(), collections.Counter()
for src, r in c.execute("SELECT source, reasons FROM answer_log WHERE ok=0 AND " + w, args):
    bysrc[src or "?"] += 1
    for x in json.loads(r or "[]"):
        cnt[x.split("(")[0][:95]] += 1
print("\nLow answers by source:", dict(bysrc))
print("\nTop reasons:")
for t, n in cnt.most_common(10):
    print("  %4d  %s" % (n, t))
print("\nQuestions most often low:")
for q, n in c.execute("SELECT question, COUNT(*) n FROM answer_log WHERE ok=0 AND " + w + " GROUP BY question ORDER BY n DESC LIMIT 10", args):
    print("  %3d  %s" % (n, q[:90]))
