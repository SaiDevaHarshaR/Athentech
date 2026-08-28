import sqlite3

# This will create a file called hospital_demo.db
conn = sqlite3.connect("hospital_demo.db")
cursor = conn.cursor()

# Create tables
cursor.execute("""
CREATE TABLE IF NOT EXISTS patients (
    uhid TEXT PRIMARY KEY,
    patient_name TEXT,
    age INTEGER,
    gender TEXT,
    registration_date TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS admissions (
    admission_id INTEGER PRIMARY KEY,
    uhid TEXT,
    admission_date TEXT,
    department TEXT,
    doctor_name TEXT,
    status TEXT
)
""")

# Insert sample data
cursor.execute("DELETE FROM patients")
cursor.execute("DELETE FROM admissions")

cursor.executemany("INSERT INTO patients VALUES (?, ?, ?, ?, ?)", [
    ('UHID001', 'Ramesh Kumar', 42, 'Male', '2026-08-20'),
    ('UHID002', 'Sita Devi', 35, 'Female', '2026-08-22'),
    ('UHID003', 'Arjun Reddy', 28, 'Male', '2026-08-24')
])

cursor.executemany("INSERT INTO admissions VALUES (?, ?, ?, ?, ?, ?)", [
    (1, 'UHID001', '2026-08-25', 'Cardiology', 'Dr. Sharma', 'Admitted'),
    (2, 'UHID002', '2026-08-26', 'Gynecology', 'Dr. Reddy', 'Admitted'),
    (3, 'UHID003', '2026-08-27', 'Orthopedics', 'Dr. Patel', 'Admitted')
])

conn.commit()
conn.close()

print("Database created successfully: hospital_demo.db")