"""Run from app folder. Adds the missing get_all_institutions_usage() that /admin/institutions-usage imports
(ImportError in service_stderr.log). Backup made, idempotent."""
import shutil, sys, time
p = "auth/usage_limiter.py"
s = open(p, encoding="utf-8").read()
if "def get_all_institutions_usage" in s:
    print("ALREADY APPLIED"); sys.exit(0)
add = '''


def get_all_institutions_usage(institutions) -> list:
    """Usage rows for the admin table. Keyed by client_prefix (same key the agent uses). Never raises."""
    out = []
    for inst in institutions or []:
        code = inst.get("client_prefix") or ""
        try:
            b = check_budget(code) if code else {"used": 0, "limit": _DEFAULT_TOKEN_LIMIT, "remaining": _DEFAULT_TOKEN_LIMIT}
        except Exception:
            b = {"used": 0, "limit": _DEFAULT_TOKEN_LIMIT, "remaining": _DEFAULT_TOKEN_LIMIT}
        limit = int(b.get("limit") or 0)
        used = int(b.get("used") or 0)
        out.append({
            "institution_name": inst.get("name") or code or "Unknown",
            "institution_code": code,
            "used": used,
            "limit": limit,
            "remaining": int(b.get("remaining") if b.get("remaining") is not None else max(0, limit - used)),
            "pct_used": min(100, round(used * 100 / limit)) if limit else 0,
        })
    return out
'''
shutil.copy2(p, p + ".bak-" + time.strftime("%Y%m%d-%H%M%S"))
open(p, "w", encoding="utf-8").write(s.rstrip("\n") + add)
print("APPLIED")
