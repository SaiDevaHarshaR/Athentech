from database.connection import get_hospital_connection
c = get_hospital_connection(
    "H023-CentromedLIS",
    "cs2.athentech.in,52434",
    "lisapp_prod",
    "Proc_Amrpp#2981J#@!",
)
print("OK" if c else "FAIL")
if not c:
    raise SystemExit
cur = c.cursor()
cur.execute(
    "SELECT TOP 10 name FROM sys.tables "
    "WHERE name LIKE '%modeofcollect%' OR name LIKE '%location%' "
    "ORDER BY name"
)
print([r[0] for r in cur.fetchall()])
cur.execute(
    "SELECT TOP 5 CAST(DATEOFBILL AS date) d, COUNT(*) n "
    "FROM trnmodeofcollectionsdet "
    "GROUP BY CAST(DATEOFBILL AS date) ORDER BY d DESC"
)
print("latest dates:", cur.fetchall())
cur.execute(
    "SELECT SUM(PAIDAMOUNT) FROM trnmodeofcollectionsdet "
    "WHERE CAST(DATEOFBILL AS date) = CAST(GETDATE() AS date)"
)
print("today sum:", cur.fetchone())
c.close()
