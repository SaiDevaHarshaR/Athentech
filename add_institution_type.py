import sqlite3
conn = sqlite3.connect("licenses.db")
conn.execute("ALTER TABLE institutions ADD COLUMN institution_type TEXT NOT NULL DEFAULT 'diagnostic'")
conn.commit()
conn.close()
print("Done.")