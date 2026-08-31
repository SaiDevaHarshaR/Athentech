
from database.license_db import init_license_db, seed_demo_institutions
init_license_db()
seed_demo_institutions()
print("licenses.db ready")