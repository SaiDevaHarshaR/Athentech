from database.connection import get_hospital_connection
c = get_hospital_connection("H023-CentromedLIS","cs2.athentech.in,52434","lisapp_prod","Proc_Amrpp#2981J#@!")
cur = c.cursor()
cur.execute("SELECT TOP 3 BILLNO FROM trnMODEOFCOLLECTIONSDET ORDER BY DATEOFBILL DESC")
print("bills:", cur.fetchall())
c.close()
