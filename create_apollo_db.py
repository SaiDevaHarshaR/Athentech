import sqlite3

conn = sqlite3.connect("hospital_apollo.db")
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS patients (
    uhid TEXT PRIMARY KEY,
    patient_name TEXT,
    age INT,
    gender TEXT,
    registration_date TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS admissions (
    admission_id INT PRIMARY KEY,
    uhid TEXT,
    admission_date TEXT,
    department TEXT,
    doctor_name TEXT,
    status TEXT
)
""")

cursor.execute("DELETE FROM patients")
cursor.execute("DELETE FROM admissions")

cursor.executemany("INSERT INTO patients VALUES (?, ?, ?, ?, ?)", [
    ("APL001", "Priya Sharma", 29, "Female", "2026-08-18"),
    ("APL002", "Vikram Singh", 45, "Male", "2026-08-19"),
    ("APL003", "Ananya Reddy", 33, "Female", "2026-08-21"),
])

cursor.executemany("INSERT INTO admissions VALUES (?, ?, ?, ?, ?, ?)", [
    (1, "APL001", "2026-08-25", "Dermatology", "Dr. Mehta", "Admitted"),
    (2, "APL002", "2026-08-26", "Cardiology", "Dr. Rao", "Admitted"),
    (3, "APL003", "2026-08-27", "Gynecology", "Dr. Iyer", "Admitted"),
])

conn.commit()
conn.close()
print("Apollo demo database created: hospital_apollo.db")