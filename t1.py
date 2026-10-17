from database.connection import get_hospital_connection
c = get_hospital_connection("H023-CentromedLIS","cs2.athentech.in,52434","lisapp_prod","Proc_Amrpp#2981J#@!")
cur = c.cursor()
for t in ["trnINVLABDET","trnINVLABPRI","trnInvStatus","mstDepartment"]:
    try:
        cur.execute(f"SELECT TOP 1 * FROM {t}")
        print(t, "OK", [x[0] for x in cur.description][:8])
    except Exception as e:
        print(t, "FAIL", e)
cur.execute("""
SELECT TOP 5 CAST(BILLDATE AS date) d, COUNT(*) n FROM trnINVLABDET
GROUP BY CAST(BILLDATE AS date) ORDER BY d DESC
""")
print("lab dates:", cur.fetchall())
c.close()
