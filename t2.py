from database.connection import get_hospital_connection
c = get_hospital_connection("H023-CentromedLIS","cs2.athentech.in,52434","lisapp_prod","Proc_Amrpp#2981J#@!")
cur = c.cursor()
cur.execute("""
SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_NAME='trnMODEOFCOLLECTIONSDET' ORDER BY ORDINAL_POSITION
""")
print([r[0] for r in cur.fetchall()])
c.close()
