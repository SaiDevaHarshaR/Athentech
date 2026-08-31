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