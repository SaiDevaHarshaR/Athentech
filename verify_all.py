"""verify_all.py - runs verify_faq.py for every client in codes.txt (same file multi_check.py uses).
  python verify_all.py --api https://api.athentech.in --codes codes.txt
Read-only. Run from the app folder."""
import argparse, subprocess, sys
ap = argparse.ArgumentParser(); ap.add_argument("--api", required=True); ap.add_argument("--codes", default="codes.txt"); a = ap.parse_args()
tot = []
for ln in open(a.codes, encoding="utf-8"):
    ln = ln.strip()
    if not ln or ln.startswith("#"): continue
    code, _, name = ln.partition(",")
    print("\n" + "=" * 70 + "\n" + (name or code) + "\n" + "=" * 70, flush=True)
    r = subprocess.run([sys.executable, "verify_faq.py", "--api", a.api, "--code", code.strip()], capture_output=True, text=True, encoding="utf-8", errors="replace")
    print(r.stdout + (r.stderr[-300:] if r.returncode else ""), flush=True)
    tot.append((name or code, [l for l in r.stdout.splitlines() if l.startswith("MATCH")]))
print("\nSUMMARY"); [print(" ", n, "|", m[0] if m else "FAILED TO RUN") for n, m in tot]
