from database.connection import get_hospital_connection
import pandas as pd

conn = get_hospital_connection()
df = pd.read_sql_query("SELECT * FROM patients", conn)
print(df)
conn.close()