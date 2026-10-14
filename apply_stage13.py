"""Sahasra Stage 13: version-guarded, idempotent source-only patch.

Usage: python apply_stage13.py --root "D:\\...\\SahasraAiAgent"
This writes timestamped backups of modified Python files. Do not run on production
until a staging test succeeds. No environment secrets are read or printed.
"""
from __future__ import annotations
import argparse
import ast
from datetime import datetime, timezone
from pathlib import Path
import re
import shutil

APP_IMPORT = 'from observability.metrics import metrics_middleware\napp.middleware("http")(metrics_middleware)\n'


def change_main(s: str) -> str:
    if 'app.middleware("http")(metrics_middleware)' in s or 'app.add_middleware(Metrics' in s:
        return s
    mark = re.search(r'^app\s*=\s*FastAPI\([^\n]*\)\s*$', s, re.M)
    if not mark:
        raise ValueError('Cannot locate simple app = FastAPI(...) line in main.py; manual review required')
    return s[:mark.end()] + '\n' + APP_IMPORT + s[mark.end():]


def change_provider(s: str) -> str:
    if '"quota_exhausted": "The provider explicitly reports a daily or monthly quota limit.' not in s:
        old = '    "rate_limited": "The provider is rate-limiting requests. Wait for its retry window, then test again.",'
        if old not in s:
            raise ValueError('llm_providers.py runtime not recognized: rate_limited message differs')
        s = s.replace(old, ('    "rate_limited": "Provider usage limit (HTTP 429). This can be a brief rate limit or a longer quota limit; check the provider dashboard or Retry-After.",\n'
                            '    "quota_exhausted": "The provider explicitly reports a daily or monthly quota limit. Check its reset time in the provider dashboard.",'), 1)
        old_credits = '    "no_credits": "The provider reports insufficient credits or quota. Check the account billing and quotas.",'
        if old_credits not in s:
            raise ValueError('llm_providers.py runtime not recognized: no_credits message differs')
        s = s.replace(old_credits, '    "no_credits": "Provider credits or quota unavailable. Check the account plan and limits; payment is not always required.",', 1)

    # Explicit daily/monthly reporting requires a provider statement. A generic
    # RESOURCE_EXHAUSTED + 429 is ambiguous, NOT proof of exhausted credits.
    if '_PERIOD_QUOTA = re.compile' not in s:
        anchor = '_BADKEY = re.compile('
        if anchor not in s:
            raise ValueError('Cannot find BYOK regular-expression section')
        rules = ('_PERIOD_QUOTA = re.compile(\n'
                 '    r"(?:per[ _-]?day|per[ _-]?month|daily|monthly|\\bTPD\\b|\\bRPD\\b|"\n'
                 '    r"quota[_ -]?(?:per[_ -]?)?(?:day|month)|free[_ -]?tier.{0,30}(?:limit|exhausted))", re.I)\n'
                 '_AMBIGUOUS_EXHAUSTED = re.compile(r"resource_exhausted", re.I)\n')
        s = s.replace(anchor, rules + anchor, 1)

    # Preserve existing return codes expected by existing tests for errors such as
    # insufficient_quota; discriminate only when period is explicit and 429 otherwise ambiguous.
    old = ('    if status == 402 or _CREDIT.search(text):\n'
           '        return "no_credits"\n'
           '    if status == 429:\n'
           '        return "rate_limited"')
    new = ('    if status == 429 and _PERIOD_QUOTA.search(text):\n'
           '        return "quota_exhausted"\n'
           '    if status == 429 and _AMBIGUOUS_EXHAUSTED.search(text) and not re.search(r"billing|credit balance|insufficient[_ -]?quota", text, re.I):\n'
           '        return "rate_limited"\n'
           '    if status == 402 or _CREDIT.search(text):\n'
           '        return "no_credits"\n'
           '    if status == 429:\n'
           '        return "rate_limited"')
    if '    if status == 429 and _PERIOD_QUOTA.search(text):' not in s:
        if old in s:
            s = s.replace(old, new, 1)
        else:
            raise ValueError('Cannot safely locate _classify() body')

    old2 = ('    if _CREDIT.search(text):\n'
            '        return "no_credits"\n'
            '    if st == 429 or re.search(r"\\b429\\b|rate.?limit|too many requests", text, re.I):\n'
            '        return "rate_limited"')
    new2 = ('    if (st == 429 or re.search(r"\\b429\\b", text)) and _PERIOD_QUOTA.search(text):\n'
            '        return "quota_exhausted"\n'
            '    if (st == 429 or re.search(r"\\b429\\b", text)) and _AMBIGUOUS_EXHAUSTED.search(text) and not re.search(r"billing|credit balance|insufficient[_ -]?quota", text, re.I):\n'
            '        return "rate_limited"\n'
            '    if _CREDIT.search(text):\n'
            '        return "no_credits"\n'
            '    if st == 429 or re.search(r"\\b429\\b|rate.?limit|too many requests", text, re.I):\n'
            '        return "rate_limited"')
    if '    if (st == 429 or re.search(r"\\b429\\b", text)) and _PERIOD_QUOTA.search(text):' not in s:
        if old2 in s:
            s = s.replace(old2, new2, 1)
        else:
            raise ValueError('Cannot safely locate classify_runtime_error()')
    return s


def change_agent(s: str) -> str:
    substitutions = {
        '    "rate_limited": "Your AI provider is rate-limiting the key right now. Please try again in a minute.",':
        ('    "rate_limited": "Your AI provider returned a usage limit (429). It may reset in minutes or later; ask your administrator to check the provider quota dashboard.",\n'
         '    "quota_exhausted": "Your institution AI provider reports its daily or monthly quota has been reached. Ask your administrator to check its reset time.",'),
        '    "no_credits": "Your AI provider account has no credits or tokens left. Please top up the provider account (or ask your administrator to update the key).",':
        '    "no_credits": "Your institution AI account reports unavailable credits or quota. Ask your administrator to review provider limits and billing; no automatic fallback is allowed.",',
    }
    for old, new in substitutions.items():
        if old in s:
            s = s.replace(old, new, 1)
        elif new not in s:
            raise ValueError('Unknown agent.py message mapping; review manually: ' + old[:40])

    # Do not lock a provider out for 26 hours solely because of an ambiguous 429.
    # Keep the explicit provider Retry-After parsing already present.
    old_ttl = '    return _PROVIDER_FALLBACK_TTL.get(provider_name, 26 * 60 * 60) # unknown — conservative fallback'
    new_ttl = '    return 300  # ambiguous 429: recheck after 5 min; never assume a daily/monthly reset'
    if old_ttl in s:
        s = s.replace(old_ttl, new_ttl, 1)
    elif new_ttl not in s:
        raise ValueError('Unknown _extract_retry_seconds return; review manually')

    # Existing code logs the raw vendor exception, which can include message content.
    replacements = {
        'print(f"[_invoke_with_retry] REAL ERROR ({current_provider}): {e}")':
            'print(f"[_invoke_with_retry] Provider {current_provider} failed: {type(e).__name__}", flush=True)',
        'print(f"[_invoke_with_retry] \'{name}\' ALSO failed: {fallback_err}")':
            'print(f"[_invoke_with_retry] Provider {name} failed: {type(fallback_err).__name__}", flush=True)',
    }
    for old, new in replacements.items():
        if old in s:
            s = s.replace(old, new, 1)
    return s


def patch(root: Path, package: Path, dry_run=False):
    root = root.resolve()
    if not (root / 'main.py').is_file() or not (root / 'agent' / 'llm_providers.py').is_file():
        raise RuntimeError(f'Not a Sahasra source root: {root}')
    jobs = {
        root / 'main.py': change_main,
        root / 'agent' / 'llm_providers.py': change_provider,
        root / 'agent' / 'agent.py': change_agent,
    }
    prepared = {}
    for path, fn in jobs.items():
        before = path.read_text(encoding='utf-8-sig')
        after = fn(before)
        ast.parse(after, filename=str(path))
        if before != after:
            prepared[path] = after
    metrics = root / 'observability' / 'metrics.py'
    if not metrics.exists():
        content = (package / 'observability' / 'metrics.py').read_text(encoding='utf-8')
        ast.parse(content)
        prepared[metrics] = content
    req = root / 'requirements.stage13.txt'
    if not req.exists():
        prepared[req] = 'prometheus-client>=0.20,<1\n'
    if dry_run:
        return list(prepared)
    suffix = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    for path, new in prepared.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.is_file():
            backup = path.with_name(path.name + f'.before_stage13_{suffix}.bak')
            shutil.copy2(path, backup)
        path.write_text(new, encoding='utf-8')
    return list(prepared)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', required=True, type=Path)
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()
    changed = patch(args.root, Path(__file__).resolve().parent, args.dry_run)
    print('DRY RUN' if args.dry_run else 'FILES PREPARED', len(changed))
    for p in changed:
        print(' -', p)
    if not changed:
        print('Already patched; nothing modified.')


if __name__ == '__main__':
    main()
