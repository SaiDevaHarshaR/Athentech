
from database.connection import get_hospital_connection

c = get_hospital_connection(
    "H023-CentromedLIS",
    "cs2.athentech.in,52434",
    "lisapp_prod",
    "Proc_Amrpp#2981J#@!",
)
cur = c.cursor()

cur.execute("""
SELECT COLUMN_NAME
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_NAME = 'trnINVLABPRI'
ORDER BY ORDINAL_POSITION
""")
cols = [r[0] for r in cur.fetchall()]
print("Invoice columns:", cols)

for col in cols:
    if "BILL" in col.upper() and "DATE" not in col.upper():
        print("Checking bill column:", col)
        cur.execute(
            f"SELECT TOP 10 * FROM trnINVLABPRI "
            f"WHERE CAST([{col}] AS VARCHAR(100)) IN (?, ?, ?)",
            "SMN26179939", "SMN26177365", "SMN26180524"
        )
        for row in cur.fetchall():
            print(row)

c.close()

