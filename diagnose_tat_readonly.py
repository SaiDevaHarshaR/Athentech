"""Read-only Sahasra TAT diagnostic. Run from the Sahasra project root.
Usage: python diagnose_tat_readonly.py --db H022-KonnectLIS_Test --period 2026-08
Optional: --server WIN-PF0AMIS54IQ --user db_login; password via SAHASRA_DIAG_DB_PASSWORD env var.
Never writes to LIS tables. Does not display credentials or patient records.
"""
import argparse
import os
from datetime import date

from database.connection import get_hospital_connection
from reports.tat_dashboard import get_tat_compliance_dashboard


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--db', required=True)
    ap.add_argument('--period', default='2026-08', help='YYYY-MM')
    ap.add_argument('--server', default=None)
    ap.add_argument('--user', default=None)
    args = ap.parse_args()
    try:
        year, month = map(int, args.period.split('-'))
        start = date(year, month, 1)
        end = date(year + (month == 12), month % 12 + 1, 1)
    except (ValueError, TypeError):
        ap.error('--period must be YYYY-MM')
    pw = os.getenv('SAHASRA_DIAG_DB_PASSWORD') or None
    conn = get_hospital_connection(args.db, args.server, args.user, pw)
    if not conn:
        print('Connection failed. Verify institution-specific server and credentials.')
        return
    try:
        cur = conn.cursor()
        cur.timeout = 60
        cur.execute('SELECT @@SERVERNAME, DB_NAME(), SYSTEM_USER')
        server, db, login = cur.fetchone()
        print('CONNECTED SERVER:', server)
        print('CONNECTED DATABASE:', db)
        print('CONNECTED SQL LOGIN:', login)
        cur.execute('''
            SELECT COUNT(*) AS AllResults,
             COALESCE(SUM(CASE WHEN s.SAMPLECOLLECTEDDATE IS NOT NULL
               AND s.RESULTENTRYDATE >= s.SAMPLECOLLECTEDDATE
               AND s.RESULTENTRYDATE < DATEADD(DAY,7,s.SAMPLECOLLECTEDDATE)
               AND inv.TATTYPE IN ('Hours','Days')
               AND TRY_CAST(inv.TATTIME AS INT)>0 THEN 1 ELSE 0 END),0) AS Eligible
            FROM trnInvStatus s
            JOIN mstInvestigations inv ON s.TCODE=inv.INVCODE
            WHERE s.RESULTENTRYDATE >= ? AND s.RESULTENTRYDATE < ?''',
            (start.isoformat(),end.isoformat()))
        all_results, eligible = cur.fetchone()
        print('RESULTS IN PERIOD:', all_results)
        print('ELIGIBLE TAT IN PERIOD:', eligible)
    except Exception as e:
        print('READ-ONLY COUNT FAILED:', type(e).__name__, str(e))
    finally:
        conn.close()
    try:
        result = get_tat_compliance_dashboard(
            'month:' + args.period, args.db, args.server, args.user, pw)
        print('DIRECT DASHBOARD RESULT:', {
            k:v for k,v in result.items()
            if k in ('period_label','completed','within_tat','outside_tat','compliance_pct','error','message')
        })
    except Exception as e:
        print('DIRECT DASHBOARD FAILED:', type(e).__name__, str(e))

if __name__ == '__main__':
    main()
