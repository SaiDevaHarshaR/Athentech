from database.connection import get_hospital_connection

c = get_hospital_connection(
    "H023-CentromedLIS", "cs2.athentech.in,52434",
    "lisapp_prod", "Proc_Amrpp#2981J#@!",
)
cur = c.cursor()

# What code typically assumes
EXPECTED = {
    "mstPatientRegistration": ["ID", "UHID", "REGDATE", "REGISTRATIONDATE", "PATIENTNAME", "NAME", "AGE", "GENDER", "LOCATIONID"],
    "trnMODEOFCOLLECTIONSDET": ["DATEOFBILL", "PAIDAMOUNT", "TOTALAMOUNT", "DUEAMOUNT", "CONCESSIONAMOUNT", "MODE", "LOCATIONID", "BILLNO", "TYPE", "STATUS"],
    "trnINVLABDET": ["BILLDATE", "BILLNO", "UHID", "PATID", "LOCATIONID", "TESTSTATUS", "DEPTCODE", "TCODE", "CHARGE"],
    "trnINVLABPRI": ["BILLNO", "BILLDATE", "UHID", "PATIENTID", "TOTALCHARGES", "PAIDAMOUNT", "CONCESSIONAMT", "CREDITAMOUNT", "LOCATIONID", "STATUS"],
    "trnInvStatus": ["BILLNO", "BILLDATE", "STATUS", "UHID", "PATIENTID", "TCODE"],
    "mstLocation": ["LOCATIONID", "LOCATIONNAME", "ACTIVE"],
    "mstDepartment": ["DEPARTMENTID", "DEPARTMENTNAME", "ACTIVE"],
    "mstInvestigations": ["INVNAME", "TCODE", "RATE"],
    "mstSubDepartment": ["SubDepartmentID", "SubDeptName", "DEPARTMENTID"],
}

def cols(table):
    cur.execute("""
        SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_NAME = ? ORDER BY ORDINAL_POSITION
    """, (table,))
    return [r[0] for r in cur.fetchall()]

def table_exists(table):
    cur.execute("SELECT 1 FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = ?", (table,))
    return cur.fetchone() is not None

print("=== TABLE / COLUMN CHECK ===\n")
for table, need in EXPECTED.items():
    if not table_exists(table):
        # try case variants
        cur.execute("""
            SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES
            WHERE LOWER(TABLE_NAME) = LOWER(?)
        """, (table,))
        row = cur.fetchone()
        if not row:
            print(f"MISSING TABLE: {table}")
            continue
        table = row[0]
        print(f"TABLE CASE: wanted different, actual={table}")
    actual = cols(table)
    actual_u = {x.upper(): x for x in actual}
    print(f"\n[{table}] {len(actual)} columns")
    for n in need:
        if n.upper() in actual_u:
            print(f"  OK   {n} -> {actual_u[n.upper()]}")
        else:
            print(f"  MISS {n}")
    # date-like / amount-like hints when something missing
    dates = [x for x in actual if "DATE" in x.upper() or x.upper().endswith("DT")]
    amts = [x for x in actual if any(k in x.upper() for k in ("AMT", "AMOUNT", "PAID", "TOTAL", "DUE", "CHARGE", "RATE"))]
    print(f"  date-like: {dates[:12]}")
    print(f"  amount-like: {amts[:12]}")

print("\n=== QUICK DATA PROBES ===\n")

probes = [
    ("patients latest REGDATE",
     "SELECT TOP 3 CAST(REGDATE AS date), COUNT(*) FROM mstPatientRegistration GROUP BY CAST(REGDATE AS date) ORDER BY 1 DESC"),
    ("lab latest BILLDATE",
     "SELECT TOP 3 CAST(BILLDATE AS date), COUNT(*) FROM trnINVLABDET GROUP BY CAST(BILLDATE AS date) ORDER BY 1 DESC"),
    ("coll paid vs total today",
     "SELECT SUM(PAIDAMOUNT), SUM(TOTALAMOUNT), SUM(DUEAMOUNT), COUNT(*) FROM trnMODEOFCOLLECTIONSDET WHERE CAST(DATEOFBILL AS date)=CAST(GETDATE() AS date)"),
    ("invlabpri amounts today",
     "SELECT TOP 1 COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME='trnINVLABPRI' AND COLUMN_NAME LIKE '%PAID%'"),
]

for label, sql in probes:
    try:
        cur.execute(sql)
        print(label, "->", cur.fetchall()[:5])
    except Exception as e:
        print(label, "-> FAIL:", e)

# trnINVLABPRI real amount column names
try:
    cur.execute("""
        SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_NAME='trnINVLABPRI'
          AND (COLUMN_NAME LIKE '%AMT%' OR COLUMN_NAME LIKE '%AMOUNT%'
               OR COLUMN_NAME LIKE '%PAID%' OR COLUMN_NAME LIKE '%TOTAL%'
               OR COLUMN_NAME LIKE '%CHARGE%')
        ORDER BY ORDINAL_POSITION
    """)
    print("trnINVLABPRI money cols ->", [r[0] for r in cur.fetchall()])
except Exception as e:
    print("trnINVLABPRI money cols FAIL", e)

c.close()
print("\nDONE")
