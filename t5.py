from database.connection import get_hospital_connection
c = get_hospital_connection("H023-CentromedLIS","cs2.athentech.in,52434","lisapp_prod","Proc_Amrpp#2981J#@!")
cur = c.cursor()
cur.execute("SELECT TOP 5 INVNAME FROM mstInvestigations WHERE INVNAME LIKE '%CBP%' OR INVNAME LIKE '%Urine%'")
print(cur.fetchall())
c.close()
