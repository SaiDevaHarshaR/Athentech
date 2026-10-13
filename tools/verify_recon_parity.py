"""READ-ONLY reconciliation comparison against an ALREADY-SAVED LIS report.

This utility NEVER executes dbo.LabDayCollection_All. That stored procedure
DELETEs and INSERTs client data, even if a caller attempts a rollback. It is
not safe as a production validation method.

Default: load an existing historical snapshot from trnTempDayCollAll (SELECT
only). Alternative: --reference exports.csv containing LOCATIONID and all 32
numeric SP output fields. Missing snapshots/columns or branches FAIL; an empty
reference can never produce a passing result. The comparison is evidence for
one date/client, NOT a certificate for every client.

  python tools/verify_recon_parity.py --code TEST_CODE --date 2026-09-18
  python tools/verify_recon_parity.py --code TEST_CODE --date 2026-09-18 --reference exported_original.csv

No client DB writes, DDL, stored procedures, or rollback tricks.
"""
import argparse
import csv
import os
import sys
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.connection import get_hospital_connection
from reports.day_collection_readonly import get_day_collection_all_branches_readonly
from reports.day_collection_reconciliation import _COLUMNS

COLS = [c for c in _COLUMNS if c not in ('USERID', 'LOCATION', 'BILLDATE', 'LOCATIONID', 'CREATEDATE')]
assert len(COLS) == 32


def compare(real_rows, mine_branches, tol=Decimal('0.01')):
    """All branches & every numeric column must be present. Returns discrepancies."""
    diffs = []
    if not real_rows:
        return [('(all branches)', '(reference)', 'missing historical report', 'not verified')]
    if not mine_branches:
        return [('(all branches)', '(computed)', 'historical data exists', 'no calculated data')]
    def key(r):
        return str(r.get('LOCATIONID', '')).strip().upper()
    mine, real = {}, {}
    for source, rows, dest in [('computed', mine_branches, mine), ('reference', real_rows, real)]:
        for r in rows:
            k = key(r)
            if not k:
                diffs.append((source, 'LOCATIONID', 'non-empty ID', 'missing ID'))
            elif k in dest:
                diffs.append((k, '(duplicate)', f'one {source} row', 'multiple rows'))
            else:
                dest[k] = r
    for k in sorted(set(real) | set(mine)):
        a, b = real.get(k), mine.get(k)
        if a is None:
            diffs.append((k, '(branch)', 'absent in reference', 'present in computed'))
            continue
        if b is None:
            diffs.append((k, '(branch)', 'present in reference', 'absent in computed'))
            continue
        for c in COLS:
            if c not in a or c not in b:
                diffs.append((k, c, 'required', 'missing field'))
                continue
            try:
                x = Decimal(str(a[c] if a[c] is not None and a[c] != '' else '0'))
                y = Decimal(str(b[c] if b[c] is not None and b[c] != '' else '0'))
                if not x.is_finite() or not y.is_finite() or abs(x-y) > (Decimal(0) if c == 'TOTALBILLS' else tol):
                    diffs.append((k, c, str(x), str(y)))
            except (InvalidOperation, ValueError, TypeError):
                diffs.append((k, c, str(a.get(c)), str(b.get(c))))
    return diffs


def _reference_csv(filename):
    with Path(filename).open(newline='', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise ValueError('Reference CSV is missing its header.')
        fields = {x.upper().strip(): x for x in reader.fieldnames}
        missing = sorted(set(COLS + ['LOCATIONID']) - set(fields))
        if missing:
            raise ValueError('Reference CSV missing fields: ' + ', '.join(missing))
        return [{c: r[fields[c]] for c in COLS + ['LOCATIONID']}
                for r in reader]


def _existing_snapshot(conn, report_date, user_id=None):
    """Only SELECT existing historical rows. This must not generate new ones."""
    cur = conn.cursor()
    if not user_id:
        cur.execute(
            "SELECT TOP 1 USERID FROM trnTempDayCollAll "
            "WHERE BILLDATE >= CONVERT(DATETIME, ?, 23) "
            "AND BILLDATE < DATEADD(DAY,1,CONVERT(DATETIME, ?, 23)) "
            "GROUP BY USERID ORDER BY MAX(CREATEDATE) DESC",
            (report_date, report_date),
        )
        r = cur.fetchone()
        if not r:
            return []
        user_id = r[0]
    cur.execute(
        "SELECT * FROM trnTempDayCollAll WHERE USERID = ? "
        "AND BILLDATE >= CONVERT(DATETIME, ?, 23) "
        "AND BILLDATE < DATEADD(DAY,1,CONVERT(DATETIME, ?, 23))",
        (user_id, report_date, report_date),
    )
    names = [d[0].upper() for d in cur.description]
    return [dict(zip(names, row)) for row in cur.fetchall()]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--code', help='Existing test institution activation code')
    ap.add_argument('--db'); ap.add_argument('--server'); ap.add_argument('--user')
    ap.add_argument('--password-env', default='LIS_PARITY_PASSWORD', help='Environment variable containing DB password')
    ap.add_argument('--date', required=True, help='YYYY-MM-DD (snapshot must already exist)')
    ap.add_argument('--reference', help='Previously exported ORIGINAL report CSV; does not run stored procedure')
    ap.add_argument('--user-id', help='Optional original report USERID, for an existing saved report')
    args = ap.parse_args()
    try:
        day = date.fromisoformat(args.date).isoformat()
    except ValueError:
        ap.error('date must be a real YYYY-MM-DD date')
    if args.code:
        from auth.license_service import validate_license
        v = validate_license(args.code)
        if not v.get('valid'):
            sys.exit('ERROR: Invalid activation code')
        db, server, user, pwd = v.get('db_name'), v.get('db_server'), v.get('db_user'), v.get('db_password')
    else:
        if not args.db:
            ap.error('--code or --db is required')
        db, server, user, pwd = args.db, args.server, args.user, os.environ.get(args.password_env)
    result = get_day_collection_all_branches_readonly(day, db, server, user, pwd)
    if 'error' in result:
        sys.exit('FAIL: SELECT-only report error: ' + result['error'])
    if args.reference:
        try:
            reference = _reference_csv(args.reference)
        except Exception as e:
            sys.exit('FAIL: Invalid reference file: ' + str(e))
    else:
        conn = get_hospital_connection(db, server, user, pwd)
        if not conn:
            sys.exit('FAIL: Could not connect to client database')
        try:
            reference = _existing_snapshot(conn, day, args.user_id)
        except Exception as e:
            sys.exit('FAIL: Could not SELECT original saved report: ' + str(e))
        finally:
            conn.close()
    diffs = compare(reference, result.get('branches', []))
    print('Reference branches:', len(reference), '| Computed branches:', len(result.get('branches', [])))
    print('Numeric fields compared per branch:', len(COLS), '| Mismatches:', len(diffs))
    for loc, field, orig, computed in diffs[:100]:
        print(f'{loc}: {field}: original={orig} computed={computed}')
    if len(diffs) > 100:
        print('...additional mismatches:', len(diffs)-100)
    if diffs:
        sys.exit(1)
    print('PASS: This date matches an existing original historical report. No client database writes were performed.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
