import sqlite3

conn = sqlite3.connect("hospital_demo.db")
cursor = conn.cursor()

# ---------- Existing tables ----------
cursor.execute("""
CREATE TABLE IF NOT EXISTS patients (
    uhid TEXT PRIMARY KEY,
    patient_name TEXT,
    age INTEGER,
    gender TEXT,
    registration_date TEXT,
    phone TEXT,
    blood_group TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS admissions (
    admission_id INTEGER PRIMARY KEY,
    uhid TEXT,
    admission_date TEXT,
    department TEXT,
    doctor_name TEXT,
    status TEXT,                -- Admitted / Discharged / Transferred
    ward_id TEXT,
    bed_number TEXT
)
""")

# ---------- NEW MODULES ----------

# Wards & Beds
cursor.execute("""
CREATE TABLE IF NOT EXISTS wards (
    ward_id TEXT PRIMARY KEY,
    ward_name TEXT,
    department TEXT,
    total_beds INTEGER,
    occupied_beds INTEGER,
    available_beds INTEGER
)
""")

# Lab
cursor.execute("""
CREATE TABLE IF NOT EXISTS labs (
    lab_id INTEGER PRIMARY KEY,
    uhid TEXT,
    test_name TEXT,
    status TEXT,                -- Pending / In Progress / Completed
    ordered_date TEXT,
    completed_date TEXT,
    result TEXT,
    doctor_name TEXT
)
""")

# Pharmacy
cursor.execute("""
CREATE TABLE IF NOT EXISTS pharmacy (
    medicine_id INTEGER PRIMARY KEY,
    medicine_name TEXT,
    stock_quantity INTEGER,
    unit TEXT,
    expiry_date TEXT,
    location TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS prescriptions (
    prescription_id INTEGER PRIMARY KEY,
    uhid TEXT,
    medicine_name TEXT,
    dosage TEXT,
    quantity INTEGER,
    prescribed_by TEXT,
    prescribed_date TEXT,
    status TEXT                 -- Pending / Dispensed
)
""")

# Clear old data
for table in ["patients", "admissions", "wards", "labs", "pharmacy", "prescriptions"]:
    cursor.execute(f"DELETE FROM {table}")

# Sample data
cursor.executemany("INSERT INTO patients VALUES (?,?,?,?,?,?,?)", [
    ('UHID001', 'Ramesh Kumar', 42, 'Male', '2026-08-20', '9876543210', 'B+'),
    ('UHID002', 'Sita Devi', 35, 'Female', '2026-08-22', '9876543211', 'O+'),
    ('UHID003', 'Arjun Reddy', 28, 'Male', '2026-08-24', '9876543212', 'A+'),
])

cursor.executemany("INSERT INTO admissions VALUES (?,?,?,?,?,?,?,?)", [
    (1, 'UHID001', '2026-08-25', 'Cardiology', 'Dr. Sharma', 'Admitted', 'WARD-CARD', 'C-12'),
    (2, 'UHID002', '2026-08-26', 'Gynecology', 'Dr. Reddy', 'Admitted', 'WARD-GYN', 'G-05'),
    (3, 'UHID003', '2026-08-27', 'Orthopedics', 'Dr. Patel', 'Admitted', 'WARD-ORTHO', 'O-08'),
])

cursor.executemany("INSERT INTO wards VALUES (?,?,?,?,?,?)", [
    ('WARD-CARD', 'Cardiology Ward', 'Cardiology', 20, 12, 8),
    ('WARD-GYN', 'Gynecology Ward', 'Gynecology', 15, 9, 6),
    ('WARD-ORTHO', 'Orthopedics Ward', 'Orthopedics', 18, 11, 7),
    ('WARD-ICU', 'ICU', 'Critical Care', 10, 8, 2),
])

cursor.executemany("INSERT INTO labs VALUES (?,?,?,?,?,?,?,?)", [
    (1, 'UHID001', 'CBC', 'Completed', '2026-08-25', '2026-08-25', 'Normal', 'Dr. Sharma'),
    (2, 'UHID001', 'ECG', 'Completed', '2026-08-25', '2026-08-25', 'Mild abnormality', 'Dr. Sharma'),
    (3, 'UHID002', 'Blood Sugar', 'Pending', '2026-08-26', None, None, 'Dr. Reddy'),
    (4, 'UHID003', 'X-Ray Knee', 'In Progress', '2026-08-27', None, None, 'Dr. Patel'),
])

cursor.executemany("INSERT INTO pharmacy VALUES (?,?,?,?,?,?)", [
    (1, 'Paracetamol 500mg', 450, 'Tablets', '2027-03-15', 'Shelf A1'),
    (2, 'Amoxicillin 250mg', 120, 'Capsules', '2026-12-01', 'Shelf B3'),
    (3, 'Insulin Glargine', 35, 'Vials', '2026-11-20', 'Fridge 2'),
    (4, 'ORS Packets', 800, 'Packets', '2028-01-10', 'Shelf C2'),
])

cursor.executemany("INSERT INTO prescriptions VALUES (?,?,?,?,?,?,?,?)", [
    (1, 'UHID001', 'Paracetamol 500mg', '1-0-1', 10, 'Dr. Sharma', '2026-08-25', 'Dispensed'),
    (2, 'UHID002', 'Amoxicillin 250mg', '1-0-1', 15, 'Dr. Reddy', '2026-08-26', 'Pending'),
])

conn.commit()
conn.close()
print("✅ Full demo database created with Labs, Pharmacy, Wards modules")