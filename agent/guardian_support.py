"""Read-only Guardian support functions. No client DML, no arbitrary command execution."""
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SNAP_DIR = ROOT / 'logs' / 'guardian_snapshots'
GUIDES = {
 'database_connection': [('Check whether only one institution is affected.', 'Open Guardian Status and confirm other clients are healthy.'), ('Check SQL Server availability', 'Ask the database administrator to verify server/network and the dedicated read-only login.'), ('Retry a safe check', 'Wait one minute, then run Self-check. If it still fails, escalate with the diagnostic report.')],
 'schema_changed': [('Refresh the detected schema', 'Use Refresh profile for this client only.'), ('Review mapping', 'Use Client diagnostics to find rejected config pins or missing columns.'), ('Escalate', 'If still missing, ask the LIS vendor to confirm renamed columns. Do not edit client tables.')],
 'query_timeout': [('Reduce report scope', 'Try today instead of a whole month.'), ('Examine database performance', 'Ask a DBA to inspect indexes and blocking with read-only diagnostics.')],
 'licensing': [('Check institution and license', 'Use the existing admin license screen to confirm activation status and expiry.')],
 'llm_provider': [('Check provider status', 'Review API quota and model availability in admin.'), ('Use instant actions', 'Test a built-in instant question while AI service is limited.')],
 'report_export': [('Try a small report', 'Test today, one location, and confirm available disk space.'), ('Compare to source', 'Never accept a zero amount without checking source fields and metric.')],
 'unknown': [('Capture evidence', 'Download a sanitized diagnostic report.'), ('Escalate', 'Send it to the appointed support developer; do not restart databases or modify client data.')],
}

def guide(category):
    return [{'step': a, 'instruction': b} for a,b in GUIDES.get(category, GUIDES['unknown'])]

def safe_client(value):
    # Reject special characters to prevent path traversal and log corruption.
    if not isinstance(value,str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}',value):
        raise ValueError('Invalid client identifier')
    return value

def inspect_columns(conn):
    """Metadata only. No client data returned."""
    cur = conn.cursor()
    cur.execute('SELECT TABLE_SCHEMA, TABLE_NAME, COLUMN_NAME, DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS ORDER BY TABLE_SCHEMA, TABLE_NAME, ORDINAL_POSITION')
    return [dict(schema=str(r[0]),table=str(r[1]),column=str(r[2]),type=str(r[3])) for r in cur.fetchall()]

def compare_snapshot(client, columns, save=False):
    """Comparison with previous known snapshot; first scan becomes baseline when save=True."""
    safe_client(client)
    current = sorted(f"{r['schema']}.{r['table']}.{r['column']}:{r['type']}" for r in columns)
    path = SNAP_DIR / (client + '.json')
    previous = None
    if path.exists():
        previous = json.loads(path.read_text(encoding='utf-8'))
    result = {'baseline_exists': previous is not None, 'added': sorted(set(current)-set(previous or [])) if previous is not None else [],
              'removed': sorted(set(previous)-set(current)) if previous is not None else [], 'column_count': len(current), 'snapshot_saved':False}
    if save:
        SNAP_DIR.mkdir(parents=True,exist_ok=True)
        tmp = path.with_suffix('.tmp')
        tmp.write_text(json.dumps(current,indent=2),encoding='utf-8')
        os.replace(tmp,path)
        result['snapshot_saved']=True
    return result

def diagnostic_report(status, client=None):
    """Support bundle without activation codes, patient records, credentials or raw SQL."""
    rows = status.get('clients',[])
    if client:
        rows = [r for r in rows if r.get('client') == client]
    data = {'created_utc': datetime.now(timezone.utc).isoformat(), 'clients':[]}
    for r in rows:
        last=r.get('last_error') or {}
        data['clients'].append({'client':r.get('client'),'error_count':r.get('errors_recent'),
          'circuit_open':r.get('circuit_open'), 'categories':r.get('by_category'),
          'last_category':last.get('category'), 'explanation':last.get('message'),
          'safe_action':last.get('safe_action'), 'guide':guide(last.get('category'))})
    return data
