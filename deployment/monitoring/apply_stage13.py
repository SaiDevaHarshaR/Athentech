"""Stage13 safe app integration for existing Sahasra FastAPI source.
Backs up main.py, validates changes before writing, and is idempotent.
"""
from pathlib import Path
from datetime import datetime
import sys

IMPORT_METRICS = 'from observability.metrics import metrics_middleware'
INSTALL_METRICS = 'app.middleware("http")(metrics_middleware)'
IMPORT_SUMMARY = 'from observability.ops_summary import summary as ops_summary'
ROUTE = '''\n@app.get("/admin/ops/summary")\ndef sahasra_ops_summary(admin: str = Depends(require_admin)):\n    """Per-worker aggregate counters; authenticated administrators only."""\n    return ops_summary()\n'''

def apply(root):
    root = Path(root).resolve()
    main = root / 'main.py'
    if not main.is_file():
        raise RuntimeError('Missing main.py in chosen Sahasra source folder')
    for name in ('metrics.py', 'ops_summary.py'):
        if not (root / 'observability' / name).is_file():
            raise RuntimeError('Missing observability/' + name + '; copy ZIP folders first')
    text = main.read_text(encoding='utf-8-sig')
    if not all(marker in text for marker in ('from fastapi import', 'app = FastAPI(', 'require_admin', 'Depends(')):
        raise RuntimeError('Unrecognized Sahasra main.py; no changes made')
    if text.count('app = FastAPI(') != 1:
        raise RuntimeError('More than one FastAPI app initialization; manual review needed')
    if 'def sahasra_ops_summary(' in text and ('@app.get("/admin/ops/summary")' not in text):
        raise RuntimeError('Existing ops summary function differs; manual review needed')
    lines=[]
    if IMPORT_METRICS not in text:
        lines.append(IMPORT_METRICS)
    if IMPORT_SUMMARY not in text:
        lines.append(IMPORT_SUMMARY)
    if lines:
        # Insert imports next to FastAPI app construction, rather than before the guarded bootstrap.
        pos=text.index('app = FastAPI(')
        text=text[:pos] + '\n'.join(lines) + '\n' + text[pos:]
    if INSTALL_METRICS not in text:
        import re
        m=re.search(r'^app\s*=\s*FastAPI\([^\n]*\)[ \t]*$',text,re.M)
        if not m:
            raise RuntimeError('Cannot safely locate a one-line app = FastAPI(...); no changes made')
        text=text[:m.end()]+'\n'+INSTALL_METRICS+text[m.end():]
    if 'def sahasra_ops_summary(' not in text:
        text += '\n'+ROUTE
    orig=main.read_text(encoding='utf-8-sig')
    if text == orig:
        return False
    compile(text, str(main), 'exec')
    backup = main.with_name('main.py.stage13-backup-'+datetime.now().strftime('%Y%m%d-%H%M%S'))
    backup.write_text(orig, encoding='utf-8')
    main.write_text(text,encoding='utf-8')
    print('Backup:',backup)
    return True

if __name__=='__main__':
    root=Path(sys.argv[1]) if len(sys.argv)>1 else Path.cwd()
    print('APPLIED' if apply(root) else 'ALREADY APPLIED')
