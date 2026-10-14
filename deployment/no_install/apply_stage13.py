"""Patch existing main.py to register optional Ops Lite; safe, idempotent.

Usage: python deployment/no_install/apply_stage13.py main.py --dry-run
       python deployment/no_install/apply_stage13.py main.py
"""
from pathlib import Path
import argparse
import sys

ANCHOR = 'app = FastAPI(title="Sahasra AI Agent")'
INSERT = '\nfrom observability.ops_lite import install as install_ops_lite\ninstall_ops_lite(app, require_admin)\n'


def patch(filepath, dry_run=False):
    src = Path(filepath)
    before = src.read_text(encoding='utf-8-sig')
    if 'install_ops_lite(app, require_admin)' in before:
        return 'Already patched. No changes.'
    if before.count(ANCHOR) != 1:
        raise RuntimeError('Expected precisely one FastAPI app creation. No changes made.')
    after = before.replace(ANCHOR, ANCHOR + INSERT, 1)
    compile(after, str(src), 'exec')
    if dry_run:
        return 'DRY RUN PASS: syntax and insertion point verified; no files modified.'
    backup = src.parent / (src.name + '.pre-ops-lite.bak')
    if backup.exists():
        raise RuntimeError('Backup exists: ' + str(backup) + '. Refusing to overwrite.')
    backup.write_text(before, encoding='utf-8')
    try:
        src.write_text(after, encoding='utf-8')
    except Exception:
        src.write_text(before, encoding='utf-8')
        raise
    return 'Patched ' + str(src) + ' (backup ' + str(backup) + ')'


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('main', nargs='?', default='main.py')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    print(patch(args.main, args.dry_run))
