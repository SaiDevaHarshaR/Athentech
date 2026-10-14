"""Safely inserts one admin-only operational-summary route into existing main.py.
Use only against a staging *copy* of the project. Idempotent; refuses unknown layouts.
"""
from pathlib import Path
import sys

IMPORT = 'from observability.ops_summary import summary as ops_summary\n'
ROUTE = '''\n@app.get("/admin/ops/summary")\ndef sahasra_ops_summary(admin: str = Depends(require_admin)):\n    """Aggregate-only, per-process metrics; authenticated admin access required."""\n    return ops_summary()\n'''

def apply(root):
    main = Path(root) / 'main.py'
    if not main.is_file():
        raise RuntimeError('main.py missing')
    text = main.read_text(encoding='utf-8')
    if 'def sahasra_ops_summary(' in text:
        return False
    if 'from fastapi import' not in text or 'require_admin' not in text or 'Depends(' not in text:
        raise RuntimeError('Not a recognized Sahasra main.py; no changes made')
    if 'from observability.metrics import metrics_middleware' not in text:
        raise RuntimeError('Stage 3 metrics middleware not installed; no changes made')
    pos = text.find('app = FastAPI(')
    if pos < 0:
        raise RuntimeError('FastAPI app not found')
    text = IMPORT + text + ROUTE
    compile(text, str(main), 'exec')
    main.write_text(text, encoding='utf-8')
    return True

if __name__ == '__main__':
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()
    print('applied' if apply(root) else 'already applied')
