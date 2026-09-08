import pyodbc

SERVER = "p2.athentech.in,52434"          # or 192.168.0.163,1433
DATABASE = "H022-KonnectLIS"              # or H022-KonnectLIS_Test
USERNAME = "lisapp_prod"                  # or sa
PASSWORD = "Proc_Amrpp#2981J#@!"

drivers_to_try = [
    "ODBC Driver 18 for SQL Server",
    "ODBC Driver 17 for SQL Server",
    "SQL Server",
]

conn = None
for driver in drivers_to_try:
    conn_str = (
        f"DRIVER={{{driver}}};"
        f"SERVER={SERVER};"
        f"DATABASE={DATABASE};"
        f"UID={USERNAME};"
        f"PWD={PASSWORD};"
        "TrustServerCertificate=yes;"
        "Encrypt=no;"
    )
    print(f"Trying: {driver}")
    try:
        conn = pyodbc.connect(conn_str, timeout=10)
        print("✅ Connected with", driver)
        break
    except Exception as e:
        print("❌", e)

if not conn:
    raise SystemExit("No connection")

cur = conn.cursor()

# 1) Tables (change LIKE to focus)
cur.execute("""
SELECT TABLE_NAME
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_TYPE = 'BASE TABLE'
  AND (
    TABLE_NAME LIKE '%collect%'
    OR TABLE_NAME LIKE '%bill%'
    OR TABLE_NAME LIKE '%pay%'
    OR TABLE_NAME LIKE '%patient%'
    OR TABLE_NAME LIKE '%lab%'
    OR TABLE_NAME LIKE '%doctor%'
    OR TABLE_NAME LIKE '%location%'
  )
ORDER BY TABLE_NAME
""")
print("\n=== Candidate tables ===")
for r in cur.fetchall():
    print("-", r[0])

# 2) Columns for one table
TABLE = "mstRefDoctor"   # change this
cur.execute("""
SELECT COLUMN_NAME, DATA_TYPE
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_NAME = ?
ORDER BY ORDINAL_POSITION
""", TABLE)
print(f"\n=== Columns: {TABLE} ===")
for r in cur.fetchall():
    print(f"- {r[0]} ({r[1]})")

# 3) Sample rows
cur.execute(f"SELECT TOP 10 * FROM [{TABLE}]")
cols = [c[0] for c in cur.description]
rows = cur.fetchall()
print(f"\n=== Sample rows: {TABLE} ===")
print(" | ".join(cols))
for row in rows:
    print(" | ".join(str(x) for x in row))

# 4) Count
cur.execute(f"SELECT COUNT(*) FROM [{TABLE}]")
print("\nCount:", cur.fetchone()[0])

conn.close()