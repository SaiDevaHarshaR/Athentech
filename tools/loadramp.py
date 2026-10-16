"""Steps the load up and shows where it starts to hurt.
   python tools/loadramp.py --url https://api.athentech.in --code KLIS-ADMIN-75605 --steps 5,10,20,40 --question "how many bills yesterday"
Uses tools/loadtest.py for every step and prints one summary table. Start with quick-report questions (no AI cost)."""
import argparse
import re
import subprocess
import sys
import os

ap = argparse.ArgumentParser()
ap.add_argument("--url", required=True)
ap.add_argument("--code", required=True)
ap.add_argument("--steps", default="5,10,20,40")
ap.add_argument("--requests", type=int, default=3)
ap.add_argument("--device", default="loadtest-1", help="one shared device id (the activation code is locked to a single device)")
ap.add_argument("--question", action="append", default=[])
a = ap.parse_args()
lt = os.path.join(os.path.dirname(os.path.abspath(__file__)), "loadtest.py")
print("%-7s %-8s %-8s %-8s %-6s" % ("users", "median", "p95", "errors", "429"))
for n in [int(x) for x in a.steps.split(",") if x.strip()]:
    cmd = [sys.executable, lt, "--url", a.url, "--code", a.code, "--users", str(n), "--requests", str(a.requests), "--device", a.device]
    for q in a.question:
        cmd += ["--question", q]
    out = subprocess.run(cmd, capture_output=True, text=True).stdout
    print("%-7d %s" % (n, " | ".join(l.strip() for l in out.strip().splitlines()[-3:])[:160]))
