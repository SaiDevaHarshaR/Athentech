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

    if not row:
        conn.close()
        return {"valid": False, "reason": "invalid_code"}

    if row["status"] not in ("Active", "Trial"):
        conn.close()
        return {"valid": False, "reason": "inactive"}

    if row["expiry_date"] < datetime.utcnow().date().isoformat():
        conn.close()
        return {"valid": False, "reason": "expired"}

    # Load institution connection settings
    inst = conn.execute(
        "SELECT * FROM institutions WHERE id = ?",
        (row["institution_id"],)
    ).fetchone()
    conn.close()

    db_name = row["db_name"]
    db_server = None
    db_user = None
    db_password = None
    hospital_name = row["hospital_name"]

    if inst:
        db_name = inst["db_name"] or db_name
        hospital_name = inst["name"] or hospital_name
        db_server = inst["db_server"]
        db_user = inst["db_user"]
        db_password = inst["db_password"]

    return {
        "valid": True,
        "code": row["code"],
        "role": row["role"],
        "db_name": db_name,
        "hospital_name": hospital_name,
        "plan": row["plan"],
        "status": row["status"],
        "expiry_date": row["expiry_date"],
        "db_server": db_server,       # None → use .env fallback later
        "db_user": db_user,
        "db_password": db_password,
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


def delete_license(code: str) -> bool:
    """
    Permanently removes a license. Unlike revoke_license (which just
    marks it Revoked so the code stops working but the record stays for
    audit history), this actually deletes the row — for cleaning up
    real junk (test codes, typos) rather than a license you might need
    to reference later.
    """
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM licenses WHERE code = ?", (code.upper(),))
    conn.commit()
    changed = cur.rowcount
    conn.close()
    return changed > 0


def _sanitize_institution(row_dict: dict) -> dict:
    """Never let the raw db_password leave this module — same pattern
    list_institutions() already used, now shared so create/update can't
    accidentally leak it back to the browser in the API response."""
    d = dict(row_dict)
    d["has_db_password"] = bool(d.get("db_password"))
    d.pop("db_password", None)
    return d


def list_institutions():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM institutions ORDER BY id ASC").fetchall()
    conn.close()
    return [_sanitize_institution(dict(r)) for r in rows]

def create_institution(
    name: str,
    client_prefix: str,
    db_name: str,
    type_: str = "Hospital",
    city: str = "",
    status: str = "Active",
    db_server: str = None,
    db_user: str = None,
    db_password: str = None,
):
    conn = get_conn()
    cur = conn.cursor()
    now = datetime.utcnow().isoformat()
    cur.execute(
        """
        INSERT INTO institutions
        (name, client_prefix, type, city, db_name, db_server, db_user, db_password, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            name,
            client_prefix.upper(),
            type_,
            city,
            db_name,
            db_server,
            db_user,
            db_password,
            status,
            now,
        ),
    )
    conn.commit()
    inst_id = cur.lastrowid
    row = cur.execute("SELECT * FROM institutions WHERE id = ?", (inst_id,)).fetchone()
    conn.close()
    return _sanitize_institution(dict(row))


def update_institution(institution_id: int, **fields):
    """
    Partial update — only fields explicitly passed are changed.
    allowed_fields = {
    "name",
    "client_prefix",
    "db_name",
    "type",
    "city",
    "status",
    "db_server",
    "db_user",
    "db_password",
}
    """
    conn = get_conn()
    cur = conn.cursor()

    existing = cur.execute("SELECT * FROM institutions WHERE id = ?", (institution_id,)).fetchone()
    if not existing:
        conn.close()
        raise ValueError("Institution not found")

    allowed_fields = {"name", "client_prefix", "db_name", "type", "city", "status", "db_server", "db_user", "db_password"}
    updates = {k: v for k, v in fields.items() if k in allowed_fields and v is not None}

    if "client_prefix" in updates:
        updates["client_prefix"] = updates["client_prefix"].upper()

    if not updates:
        conn.close()
        return _sanitize_institution(dict(existing))

    set_clause = ", ".join(f"{k} = ?" for k in updates)
    cur.execute(
        f"UPDATE institutions SET {set_clause} WHERE id = ?",
        (*updates.values(), institution_id)
    )
    conn.commit()

    updated = cur.execute("SELECT * FROM institutions WHERE id = ?", (institution_id,)).fetchone()
    conn.close()
    return _sanitize_institution(dict(updated))


def delete_institution(institution_id: int) -> dict:
    """
    Permanently removes an institution AND every license tied to it —
    otherwise deleting an institution would leave orphaned licenses
    pointing at an institution_id that no longer exists, which would
    break validate_license() the next time one of those codes is used.
    Returns how many licenses were removed alongside it, so the caller
    can tell the admin what actually happened.
    """
    conn = get_conn()
    cur = conn.cursor()

    existing = cur.execute("SELECT * FROM institutions WHERE id = ?", (institution_id,)).fetchone()
    if not existing:
        conn.close()
        raise ValueError("Institution not found")

    cur.execute("DELETE FROM licenses WHERE institution_id = ?", (institution_id,))
    licenses_removed = cur.rowcount

    cur.execute("DELETE FROM institutions WHERE id = ?", (institution_id,))
    conn.commit()
    conn.close()

    return {"institution_name": existing["name"], "licenses_removed": licenses_removed}


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


# ---------------------------------------------------------------------------
# Settings — runtime-configurable values previously hardcoded in main.py /
# guardrails.py. Stored as plain key-value text; caller is responsible for
# interpreting types (see get_settings() below, which does that conversion).
# ---------------------------------------------------------------------------

def get_settings() -> dict:
    conn = get_conn()
    rows = conn.execute("SELECT key, value FROM settings").fetchall()
    conn.close()
    raw = {r["key"]: r["value"] for r in rows}

    return {
        "license_validity_days": int(raw.get("license_validity_days", 90) or 90),
        "normal_mode_enabled": raw.get("normal_mode_enabled", "true") == "true",
        "rate_limit_per_minute": int(raw.get("rate_limit_per_minute", 300) or 300),
        "extra_blocked_patterns": [
            p.strip() for p in (raw.get("extra_blocked_patterns", "") or "").split(",") if p.strip()
        ],
        "output_redaction_enabled": raw.get("output_redaction_enabled", "true") == "true",
        "email_alerts_enabled": raw.get("email_alerts_enabled", "false") == "true",
        "webhook_url": raw.get("webhook_url", ""),
        "smtp_host": raw.get("smtp_host", ""),
        "smtp_port": int(raw.get("smtp_port", 587) or 587),
        "smtp_user": raw.get("smtp_user", ""),
        "smtp_password": raw.get("smtp_password", ""),
        "alert_email_to": raw.get("alert_email_to", ""),
    }


def update_settings(**fields) -> dict:
    conn = get_conn()
    cur = conn.cursor()

    serializers = {
        "license_validity_days": lambda v: str(int(v)),
        "normal_mode_enabled": lambda v: "true" if v else "false",
        "rate_limit_per_minute": lambda v: str(int(v)),
        "extra_blocked_patterns": lambda v: ",".join(v) if isinstance(v, list) else str(v),
        "output_redaction_enabled": lambda v: "true" if v else "false",
        "email_alerts_enabled": lambda v: "true" if v else "false",
        "webhook_url": lambda v: str(v),
        "smtp_host": lambda v: str(v),
        "smtp_port": lambda v: str(int(v)),
        "smtp_user": lambda v: str(v),
        "smtp_password": lambda v: str(v),
        "alert_email_to": lambda v: str(v),
    }

    for key, value in fields.items():
        if key not in serializers or value is None:
            continue
        cur.execute(
            "INSERT INTO settings(key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, serializers[key](value))
        )

    conn.commit()
    conn.close()
    return get_settings()