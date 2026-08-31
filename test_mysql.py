from database.connections import get_hospital_connection

conn = get_hospital_connection()
if conn:
    cursor = conn.cursor()
    cursor.execute("SHOW TABLES")
    tables = cursor.fetchall()
    print("Tables in the database:")
    for t in tables:
        print("-", t[0])
    conn.close()
else:
    print("Connection failed")