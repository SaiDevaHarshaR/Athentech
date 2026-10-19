"""B2B clients (organisations) of a white-label client: search the client's LIS, add / list / remove.
A "client" here is an organisation in the LIS (mstOrganisation), e.g. Centromed's customer 'Yashoda Labs'.
Contacts (people) belong to one organisation; a logged-in contact sees ONLY that organisation's data."""
import re
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from auth.admin_auth import require_admin

router = APIRouter()
_DDL = """
IF OBJECT_ID('dbo.sahasra_b2b_orgs', 'U') IS NULL
CREATE TABLE dbo.sahasra_b2b_orgs (
    institution_id INT NOT NULL,
    organisation_code NVARCHAR(80) NOT NULL,
    organisation_name NVARCHAR(200) NULL,
    created_by NVARCHAR(100) NULL,
    created_at DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME(),
    PRIMARY KEY (institution_id, organisation_code)
)"""
_ready = False


def _admin():
    global _ready
    from auth import b2b_portal as b
    conn = b._admin_conn()
    if not _ready:
        conn.execute(_DDL)
        conn.commit()
        _ready = True
    return conn


def _lis_rows(inst, sql, params=()):
    from auth import b2b_portal as b
    conn = b._lis(inst)
    try:
        return conn.execute(sql, params).fetchall()
    finally:
        try: conn.close()
        except Exception: pass


def resolve_org(inst, text):
    """Organisation code or (part of) a name -> (code, name). Raises HTTPException 422 when none / ambiguous."""
    t = (text or "").strip()
    if not t:
        raise HTTPException(422, "Give an organisation code or name.")
    if re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", t):
        r = _lis_rows(inst, "SELECT TOP 1 ORGANISATIONCODE, ORGANISATIONNAME FROM mstOrganisation WHERE ORGANISATIONCODE = ?", (t.upper(),))
        if r:
            return str(r[0][0]), str(r[0][1])
    like = "%" + t.replace("%", "").replace("[", "").replace("_", "") + "%"
    r = _lis_rows(inst, "SELECT TOP 6 ORGANISATIONCODE, ORGANISATIONNAME FROM mstOrganisation WHERE ORGANISATIONNAME LIKE ? ORDER BY ORGANISATIONNAME", (like,))
    if len(r) == 1:
        return str(r[0][0]), str(r[0][1])
    if not r:
        raise HTTPException(422, "No organisation matching '%s' in this client's database." % t)
    raise HTTPException(422, "More than one match - use the code: " + "; ".join("%s = %s" % (x[1], x[0]) for x in r))


def ensure_org(inst_id, code, name, admin):
    conn = _admin()
    try:
        if not conn.execute("SELECT 1 FROM dbo.sahasra_b2b_orgs WHERE institution_id=? AND organisation_code=?", (inst_id, code)).fetchone():
            conn.execute("INSERT INTO dbo.sahasra_b2b_orgs (institution_id, organisation_code, organisation_name, created_by) VALUES (?,?,?,?)",
                         (inst_id, code, (name or "")[:200], admin))
            conn.commit()
    finally:
        conn.close()


@router.get("/admin/b2b/orgs/search")
def search_orgs(institution_id: int = Query(..., gt=0), q: str = Query("", max_length=80), admin: str = Depends(require_admin)):
    from auth import b2b_portal as b
    inst = b._institution_by_id(institution_id)
    if not inst:
        raise HTTPException(404, "Institution not found")
    t = q.strip().replace("%", "").replace("[", "").replace("_", "")
    like = "%" + t + "%"
    rows = _lis_rows(inst, "SELECT TOP 25 ORGANISATIONCODE, ORGANISATIONNAME, ACTIVE, CONTACTPERSON, ISCREDIT FROM mstOrganisation "
                           "WHERE ORGANISATIONNAME LIKE ? OR ORGANISATIONCODE LIKE ? ORDER BY ORGANISATIONNAME", (like, like))
    conn = _admin()
    try:
        added = {str(r[0]) for r in conn.execute("SELECT organisation_code FROM dbo.sahasra_b2b_orgs WHERE institution_id=?", (institution_id,)).fetchall()}
        added |= {str(r[0]) for r in conn.execute("SELECT DISTINCT organisation_code FROM dbo.sahasra_b2b_contacts WHERE institution_id=?", (institution_id,)).fetchall()}
    finally:
        conn.close()
    return {"results": [{"code": str(r[0]), "name": str(r[1] or ""), "active": bool(r[2]) if r[2] is not None else True,
                         "contact_person": str(r[3] or ""), "credit": bool(r[4]) if r[4] is not None else False, "added": str(r[0]) in added} for r in rows]}


@router.get("/admin/b2b/orgs")
def list_orgs(institution_id: int = Query(..., gt=0), admin: str = Depends(require_admin)):
    conn = _admin()
    try:
        orgs = {str(r[0]): str(r[1] or "") for r in conn.execute(
            "SELECT organisation_code, organisation_name FROM dbo.sahasra_b2b_orgs WHERE institution_id=?", (institution_id,)).fetchall()}
        counts = {}
        for r in conn.execute("SELECT organisation_code, COUNT(*), SUM(CASE WHEN active=1 THEN 1 ELSE 0 END) FROM dbo.sahasra_b2b_contacts "
                              "WHERE institution_id=? GROUP BY organisation_code", (institution_id,)).fetchall():
            counts[str(r[0])] = (int(r[1]), int(r[2] or 0))
    finally:
        conn.close()
    from auth import b2b_portal as b
    inst = b._institution_by_id(institution_id)
    out = []
    for code in sorted(set(orgs) | set(counts)):
        name = orgs.get(code) or ""
        if not name and inst:
            try: name = b._org_name(inst, code) or ""
            except Exception: name = ""
        out.append({"code": code, "name": name, "contacts": counts.get(code, (0, 0))[0], "active_contacts": counts.get(code, (0, 0))[1]})
    return {"orgs": out}


class OrgIn(BaseModel):
    institution_id: int = Field(gt=0)
    organisation_code: str = Field(min_length=1, max_length=80)


@router.post("/admin/b2b/orgs")
def add_org(body: OrgIn, admin: str = Depends(require_admin)):
    from auth import b2b_portal as b
    inst = b._institution_by_id(body.institution_id)
    if not inst:
        raise HTTPException(404, "Institution not found")
    code, name = resolve_org(inst, body.organisation_code)
    ensure_org(body.institution_id, code, name, admin)
    return {"status": "success", "code": code, "name": name}


@router.delete("/admin/b2b/orgs/{code}")
def delete_org(code: str, institution_id: int = Query(..., gt=0), admin: str = Depends(require_admin)):
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", code):
        raise HTTPException(400, "Invalid organisation code.")
    conn = _admin()
    try:
        ids = [int(r[0]) for r in conn.execute("SELECT id FROM dbo.sahasra_b2b_contacts WHERE institution_id=? AND organisation_code=?", (institution_id, code)).fetchall()]
        for cid in ids:
            conn.execute("UPDATE dbo.sahasra_b2b_sessions SET revoked=1 WHERE contact_id=? AND institution_id=?", (cid, institution_id))
            conn.execute("DELETE FROM dbo.sahasra_b2b_test_otp WHERE contact_id=? AND institution_id=?", (cid, institution_id))
        conn.execute("DELETE FROM dbo.sahasra_b2b_contacts WHERE institution_id=? AND organisation_code=?", (institution_id, code))
        conn.execute("DELETE FROM dbo.sahasra_b2b_orgs WHERE institution_id=? AND organisation_code=?", (institution_id, code))
        conn.commit()
    except Exception:
        try: conn.rollback()
        except Exception: pass
        raise HTTPException(500, "Could not remove the client.")
    finally:
        conn.close()
    return {"status": "success", "removed_contacts": len(ids)}
