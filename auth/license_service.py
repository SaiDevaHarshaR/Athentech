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
    row = conn.execute(
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
    return set_license_status(code, "Revoked")


def set_license_status(code: str, status: str):
    allowed = {"Active", "Trial", "Suspended", "Revoked"}
    if status not in allowed:
        raise ValueError("Invalid status")

    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "UPDATE licenses SET status = ? WHERE code = ?",
        (status, code.upper())
    )
    conn.commit()
    changed = cur.rowcount
    conn.close()
    return changed > 0


def list_institutions():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM institutions ORDER BY id ASC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def create_institution(name, client_prefix, db_name, type_="Hospital", city="", status="Active"):
    conn = get_conn()
    cur = conn.cursor()
    now = datetime.utcnow().isoformat()
    cur.execute("""
        INSERT INTO institutions (name, client_prefix, type, city, db_name, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (name, client_prefix.upper(), type_, city, db_name, status, now))
    conn.commit()
    inst_id = cur.lastrowid
    conn.close()
    return {
        "id": inst_id,
        "name": name,
        "client_prefix": client_prefix.upper(),
        "type": type_,
        "city": city,
        "db_name": db_name,
        "status": status
    }


def get_role_permissions():
    conn = get_conn()
    rows = conn.execute("SELECT role, tables_csv FROM role_permissions").fetchall()
    conn.close()
    return {r["role"]: r["tables_csv"].split(",") for r in rows}


def update_role_permissions(role: str, tables: list):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO role_permissions(role, tables_csv) VALUES (?, ?) "
        "ON CONFLICT(role) DO UPDATE SET tables_csv = excluded.tables_csv",
        (role.lower(), ",".join(tables))
    )
    conn.commit()
    conn.close()