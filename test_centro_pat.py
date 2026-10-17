from database.connection import get_hospital_connection
c = get_hospital_connection(
    "H023-CentromedLIS", "cs2.athentech.in,52434",
    "lisapp_prod", "Proc_Amrpp#2981J#@!",
)
cur = c.cursor()

# 1) table exists?
cur.execute("""
SELECT name FROM sys.tables
WHERE name LIKE '%patient%' OR name LIKE '%regist%'
ORDER BY name
""")
print("TABLES:", [r[0] for r in cur.fetchall()])

# 2) if mstPatientRegistration exists
try:
    cur.execute("""
    SELECT TOP 5 CAST(REGISTRATIONDATE AS date) d, COUNT(*)
    FROM mstPatientRegistration
    GROUP BY CAST(REGISTRATIONDATE AS date)
    ORDER BY d DESC
    """)
    print("BY REGISTRATIONDATE:", cur.fetchall())
except Exception as e:
    print("REGISTRATIONDATE fail:", e)

try:
    cur.execute("""
    SELECT TOP 5 COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_NAME = 'mstPatientRegistration'
    ORDER BY ORDINAL_POSITION
    """)
    print("COLS sample:", [r[0] for r in cur.fetchall()])
    cur.execute("SELECT TOP 3 * FROM mstPatientRegistration ORDER BY 1 DESC")
    print("SAMPLE:", cur.fetchall()[:3])
except Exception as e:
    print("mstPatientRegistration fail:", e)

c.close()
