"""Read-only: check each LIS DB has what the B2B portal needs. Usage: python tools/b2b_schema_check.py PREFIX_or_DBNAME [...]"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from auth import b2b_portal as B

def check(inst):
    out = []
    key = inst.upper()
    c = B._admin_conn()
    try:
        rows = [B._dict(r) for r in c.execute("SELECT * FROM institutions").fetchall()]
    finally:
        c.close()
    inst = next((r for r in rows if key in (str(r.get('client_prefix') or '').upper(), str(r.get('db_name') or '').upper(), str(r.get('name') or '').upper())), None)
    if not inst:
        return ['  not found. Available (prefix | db_name | name):'] + ['    %s | %s | %s' % (r.get('client_prefix'), r.get('db_name'), r.get('name')) for r in rows]
    conn = B._lis(inst)
    try:
        for t, need in (("trnINVLABPRI", {"BILLNO", "BILLDATE", "ORGANISATIONCODE"}), ("mstOrganisation", {"ORGANISATIONCODE", "ORGANISATIONNAME"})):
            cols = B._columns(conn, t)
            out.append(f"  {t}: " + ("MISSING TABLE" if not cols else "ok" if need <= cols else "missing " + ",".join(sorted(need - cols))))
        try: out.append(f"  billing: total={B._billing_schema(conn)[0]}")
        except Exception as e: out.append(f"  billing: FAIL {getattr(e,'detail',e)}")
        r = conn.execute("SELECT DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME='trnINVLABPRI' AND COLUMN_NAME='BILLDATE'").fetchone()
        out.append(f"  BILLDATE type: {r[0] if r else '?'}" + ("  <-- text: ISO compare may misbehave" if r and 'char' in str(r[0]).lower() else ""))
    finally:
        conn.close()
    return out

if __name__ == "__main__":
    for code in sys.argv[1:]:
        print(code)
        try: print("\n".join(check(code)))
        except Exception as e: print("  ERROR", type(e).__name__, e)
