from database.connection import get_hospital_connection
c = get_hospital_connection("H023-CentromedLIS","cs2.athentech.in,52434","lisapp_prod","Proc_Amrpp#2981J#@!")
cur = c.cursor()
cur.execute("SELECT TOP 10 LOCATIONID, LOCATIONNAME FROM mstLocation")
print("locs:", cur.fetchall())
try:
    cur.execute("SELECT TOP 10 * FROM mstDepartment")
    print("depts OK", cur.fetchall()[:5])
except Exception as e:
    print("depts FAIL", e)
c.close()
