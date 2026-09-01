import pyodbc

SERVER = "192.168.0.163,1433"
DATABASE = "H022-KonnectLIS_Test"
USERNAME = "sa"
PASSWORD = "Amrpp#2981J##"

# Try modern driver first, then fallback
drivers_to_try = [
    "ODBC Driver 18 for SQL Server",
    "ODBC Driver 17 for SQL Server",
    "SQL Server",
]

last_error = None

for driver in drivers_to_try:
    conn_str = (
        f"DRIVER={{{driver}}};"
        f"SERVER={SERVER};"
        f"DATABASE={DATABASE};"
        f"UID={USERNAME};"
        f"PWD={PASSWORD};"
        "TrustServerCertificate=yes;"
        "Encrypt=no;"
    )
    print(f"\nTrying driver: {driver}")
    try:
        conn = pyodbc.connect(conn_str, timeout=5)
        cur = conn.cursor()
        cur.execute("SELECT TOP 5 name FROM sys.tables ORDER BY name")
        rows = cur.fetchall()
        print("✅ Connected successfully")
        print("Sample tables:")
        for r in rows:
            print("-", r[0])
        conn.close()
        break
    except Exception as e:
        print("❌ Failed:", e)
        last_error = e
else:
    print("\nAll drivers failed")
    print(last_error)