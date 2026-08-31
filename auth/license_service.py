from datetime import datetime, timedelta
from database.license_db import get_conn
from auth.code_generator import generate_activation_code

def create_license(
    institution_id: int,
    role: str,
    phone: str,
    dob_year: str,
    plan: str = "Standard",
    valid_days: int = 90,
    created_by: str = "admin"
):
    conn = get_conn()
    cur = conn.cursor()

    inst = cur.execute(
        "SELECT * FROM institutions WHERE id = ?",
        (institution_id,)
    ).fetchone()

    if not inst:
        conn.close()
        raise ValueError("Institution not found")

    if inst["status"] != "Active":
        conn.close()
        raise ValueError("Institution is not active")

    code = generate_activation_code(
        client_prefix=inst["client_prefix"],
        role=role,
        phone=phone,
        dob_year=dob_year
    )

    # prevent duplicate active code
    existing = cur.execute(
        "SELECT id FROM licenses WHERE code = ?",
        (code,)
    ).fetchone()
    if existing:
        conn.close()
        raise ValueError(f"Code already exists: {code}")

    expiry = (datetime.utcnow() + timedelta(days=valid_days)).date().isoformat()
    now = datetime.utcnow().isoformat()

    cur.execute("""
        INSERT INTO licenses (
            code, institution_id, client_prefix, role, plan, phone, dob_year,
            user_ref, db_name, hospital_name, status, expiry_date, created_by, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Active', ?, ?, ?)
    """, (
        code,
        institution_id,
        inst["client_prefix"],
        role.lower(),
        plan,
        phone,
        str(dob_year),
        phone,
        inst["db_name"],
        inst["name"],
        expiry,
        created_by,
        now
    ))

    conn.commit()
    license_id = cur.lastrowid
    conn.close()

    return {
        "id": license_id,
        "code": code,
        "role": role.lower(),
        "plan": plan,
        "db_name": inst["db_name"],
        "hospital_name": inst["name"],
        "status": "Active",
        "expiry_date": expiry
    }

def validate_license(code: str):
    conn = get_conn()
    cur = conn.cursor()
    row = cur.execute(
        "SELECT * FROM licenses WHERE code = ?",
        (code.upper(),)
    ).fetchone()
    conn.close()

    if not row:
        return {"valid": False, "reason": "invalid_code"}

    if row["status"] not in ("Active", "Trial"):
        return {"valid": False, "reason": "inactive"}

    if row["expiry_date"] < datetime.utcnow().date().isoformat():
        return {"valid": False, "reason": "expired"}

    return {
        "valid": True,
        "code": row["code"],
        "role": row["role"],
        "db_name": row["db_name"],
        "hospital_name": row["hospital_name"],
        "plan": row["plan"],
        "status": row["status"],
        "expiry_date": row["expiry_date"]
    }

def list_licenses():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM licenses ORDER BY id DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]

def revoke_license(code: str):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "UPDATE licenses SET status = 'Revoked' WHERE code = ?",
        (code.upper(),)
    )
    conn.commit()
    changed = cur.rowcount
    conn.close()
    return changed > 0