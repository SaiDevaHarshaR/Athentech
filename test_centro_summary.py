from database.connection import get_hospital_connection

c = get_hospital_connection(
    "H023-CentromedLIS",
    "cs2.athentech.in,52434",
    "lisapp_prod",
    "Proc_Amrpp#2981J#@!",
)

cur = c.cursor()

cur.execute("""
SELECT
    MODE,
    TYPE,
    STATUS,
    LOCATIONID,
    COUNT(*) AS cnt,
    SUM(TOTALAMOUNT) AS total,
    SUM(PAIDAMOUNT) AS paid,
    SUM(DUEAMOUNT) AS due
FROM trnMODEOFCOLLECTIONSDET
WHERE CAST(DATEOFBILL AS date) = CAST(GETDATE() AS date)
GROUP BY MODE, TYPE, STATUS, LOCATIONID
ORDER BY LOCATIONID, MODE, TYPE, STATUS
""")

print("MODE | TYPE | STATUS | LOCATION | COUNT | TOTAL | PAID | DUE")
for r in cur.fetchall():
    print(tuple(r))

c.close()
