"""
Diagnoses the "db_server/db_user falling back to .env" issue directly,
no browser/DevTools needed.

Usage:
    python diagnose_institution_connection.py <activation_code>

Example:
    python diagnose_institution_connection.py KONNE-ADMIN-1234
"""

import sys

if len(sys.argv) < 2:
    print("Usage: python diagnose_institution_connection.py <activation_code>")
    sys.exit(1)

code = sys.argv[1]

from database.license_db import get_conn

print("=" * 70)
print("STEP 1: Raw license row for this code")
print("=" * 70)
conn = get_conn()
license_row = conn.execute("SELECT * FROM licenses WHERE code = ?", (code.upper(),)).fetchone()
if not license_row:
    print(f"No license found for code '{code}'. Check you typed it correctly.")
    conn.close()
    sys.exit(1)

license_dict = dict(license_row)
print(f"institution_id: {license_dict.get('institution_id')}")
print(f"role: {license_dict.get('role')}")
print(f"status: {license_dict.get('status')}")
print(f"db_name (on the license itself): {license_dict.get('db_name')}")

print()
print("=" * 70)
print("STEP 2: Raw institution row this license points to")
print("=" * 70)
inst_row = conn.execute("SELECT * FROM institutions WHERE id = ?", (license_dict["institution_id"],)).fetchone()
conn.close()

if not inst_row:
    print(f"PROBLEM FOUND: institution_id {license_dict['institution_id']} does not exist in the institutions table!")
    print("This license is pointing at a deleted or non-existent institution.")
    sys.exit(1)

inst_dict = dict(inst_row)
print(f"institution id: {inst_dict.get('id')}")
print(f"name: {inst_dict.get('name')}")
print(f"db_name: {inst_dict.get('db_name')!r}")
print(f"db_server: {inst_dict.get('db_server')!r}")
print(f"db_user: {inst_dict.get('db_user')!r}")
print(f"db_password: {'<set, ' + str(len(inst_dict.get('db_password') or '')) + ' chars>' if inst_dict.get('db_password') else '<empty/None>'}")

print()
print("=" * 70)
print("STEP 3: What validate_license() actually returns for this code")
print("=" * 70)
from auth.license_service import validate_license
result = validate_license(code)
print(f"valid: {result.get('valid')}")
print(f"db_name: {result.get('db_name')!r}")
print(f"db_server: {result.get('db_server')!r}")
print(f"db_user: {result.get('db_user')!r}")
print(f"db_password: {'<set>' if result.get('db_password') else '<empty/None>'}")

print()
print("=" * 70)
print("DIAGNOSIS")
print("=" * 70)
if inst_dict.get("db_server") and not result.get("db_server"):
    print("BUG CONFIRMED: db_server IS saved on the institution (Step 2) but")
    print("validate_license() is NOT returning it (Step 3). The bug is inside")
    print("validate_license() itself, not the frontend or the database.")
elif not inst_dict.get("db_server"):
    print("The institution itself has no db_server saved (Step 2 shows empty).")
    print("This means the SAVE never actually worked for this specific institution")
    print("record, even if the edit form appeared to show a value.")
elif result.get("db_server"):
    print("Everything looks correct here — db_server IS being returned properly.")
    print("If the live chat is still falling back to .env, the running server")
    print("process may not have picked this up — try a full restart again,")
    print("or double check you're testing with THIS exact activation code.")