from database.connection import get_hospital_connection

c = get_hospital_connection(
    "H023-CentromedLIS",
    "cs2.athentech.in,52434",
    "lisapp_prod",
    "Proc_Amrpp#2981J#@!",
)

cur = c.cursor()

cur.execute("""
SELECT TOP 20 *
FROM trnmodeofcollectionsdet
WHERE CAST(DATEOFBILL AS date) = CAST(GETDATE() AS date)
ORDER BY DATEOFBILL DESC
""")

rows = cur.fetchall()

print("columns:", [d[0] for d in cur.description])
for r in rows:
    print(tuple(r))

c.close()
