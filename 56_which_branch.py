"""which branch highest -> fixed report
Anchor-based, idempotent (re-running says ALREADY APPLIED), backups made (.bak-<time>), all-or-nothing."""
import os, shutil, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
TS = time.strftime('%Y%m%d-%H%M%S')
NEW_FILES = []
EDITS = {'agent/intents.py': [('    if _needs_llm(q):\n        return None\n\n    if re.search(r"\\b(branch[\\s-]?wise|by branch|by location|location[\\s-]?wise|per branch|each branch)\\b", q) and "collection" in q:\n        try:\n            r1 = _handle_collection_by_location(q, role, db_name, db_server, db_user, db_password, matched_keyword="collection by branch")\n            if r1:\n', '    if _needs_llm(q):\n        return None\n\n    if re.search(r"\\b(branch[\\s-]?wise|by branch|by location|location[\\s-]?wise|per branch|each branch|which branch|top branch|best branch|highest branch|branch with the highest|branch has the highest)\\b", q) and "collection" in q:\n        try:\n            r1 = _handle_collection_by_location(q, role, db_name, db_server, db_user, db_password, matched_keyword="collection by branch")\n            if r1:\n', None)]}

def read(p):
    with open(p, encoding="utf-8", newline="") as fh: return fh.read()
plan, notes = [], []
def optional_missing(rel):          # front-end files may live elsewhere on a given server: skip instead of failing the whole patch
    top = rel.split("/")[0]
    return (top in ("widget_files", "admin")) and not os.path.isdir(top)
for rel in NEW_FILES:
    if optional_missing(rel): notes.append("skipped " + rel + " (folder not here)"); continue
    src = os.path.join(HERE, "files", rel)
    if not os.path.exists(rel) or read(rel) != read(src):
        plan.append((rel, read(src), os.path.exists(rel)))
failed = []
for rel, pairs in EDITS.items():
    if not os.path.exists(rel):
        if not rel.endswith(".py") and rel != "main.py":
            notes.append("skipped " + rel + " (not found)"); continue
        failed.append("%s not found (run from the app folder)" % rel); continue
    t = read(rel); changed = False; bad = None
    for n, (old, new, ins) in enumerate(pairs, 1):
        if '\r\n' in t:
            old, new, ins = [(x.replace('\r\n','\n').replace('\n','\r\n') if x else x) for x in (old, new, ins)]
        if ins and ins in t: continue                     # inserted text is already there (even if neighbours changed since)
        if new in t and old not in t: continue           # already applied
        if new in t and old in t and old in new: continue
        if t.count(old) != 1:
            bad = "%s: edit %d/%d - anchor %s in your file: %r" % (rel, n, len(pairs), "missing" if t.count(old) == 0 else "ambiguous", old.strip().splitlines()[0][:90] if old.strip() else old[:40]); break
        t = t.replace(old, new); changed = True
    if bad: failed.append(bad); continue                 # this file is left untouched; the other files still apply
    if changed: plan.append((rel, t, True))
if not plan and failed:
    for f in failed: print("FAILED: " + f)
    sys.exit(1)
if not plan: print("ALREADY APPLIED" + ((" (" + "; ".join(notes) + ")") if notes else "")); sys.exit(0)
for rel, text, existed in plan:
    if existed: shutil.copy2(rel, rel + ".bak-" + TS)
    os.makedirs(os.path.dirname(rel) or ".", exist_ok=True)
    with open(rel, "w", encoding="utf-8", newline="") as fh: fh.write(text)
print("APPLIED: " + ", ".join(r for r, _, _ in plan) + ((" | " + "; ".join(notes)) if notes else ""))
for f in failed: print("FAILED: " + f)
if failed: sys.exit(1)
