"""TEST-PHASE ONLY: /register in the white-label chat. Active only when B2B_TEST_REGISTER=1 in the service environment;
otherwise every call is a 404. Registers a contact for an EXISTING LIS organisation and returns a test verification code."""
import re
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

router = APIRouter()


class Reg(BaseModel):
    client: str = Field(min_length=1, max_length=50)
    phone: str = Field(min_length=8, max_length=30)
    org_code: str = Field(min_length=1, max_length=120)
    name: str = Field(default="", max_length=120)


@router.post("/public/b2b/test-register")
def test_register(body: Reg, request: Request):
    from auth import b2b_portal as b
    if not b._testreg():
        raise HTTPException(404, "Not found")
    inst = b._institution_by_prefix(body.client)
    if not inst or not b._b2b_enabled(inst):
        raise HTTPException(404, "This B2B portal is not available.")
    ip = request.client.host if request.client else "unknown"
    b._rate("testreg-ip", ip, inst["id"], "ip", 20)
    from auth.b2b_orgs_api import resolve_org, ensure_org
    code, company = resolve_org(inst, body.org_code)       # a code, or the organisation's name (e.g. "Yashoda")
    ensure_org(int(inst["id"]), code, company, "test-register")
    phone = b._phone(body.phone)
    given = (body.name or "").strip()[:120]
    if given.lower() == "test user":
        given = ""
    cname = given or (company or code)[:120]
    conn = b._admin_conn()
    try:
        row = conn.execute("SELECT id FROM dbo.sahasra_b2b_contacts WHERE institution_id=? AND phone_e164=?",
                           (inst["id"], phone)).fetchone()
        if row:
            conn.execute("UPDATE dbo.sahasra_b2b_contacts SET organisation_code=?, active=1" + (", contact_name=?" if given else "") + " WHERE institution_id=? AND phone_e164=?",
                         (code,) + ((cname,) if given else ()) + (inst["id"], phone))
        else:
            conn.execute("INSERT INTO dbo.sahasra_b2b_contacts (institution_id, organisation_code, contact_name, phone_e164, created_by) "
                         "VALUES (?,?,?,?,?)", (inst["id"], code, cname, phone, "test-register"))
        conn.commit()
    except Exception:
        try: conn.rollback()
        except Exception: pass
        raise HTTPException(500, "Could not save the contact.")
    finally:
        conn.close()
    contact = b._contact(int(inst["id"]), phone)
    if not contact:
        raise HTTPException(500, "Could not save the contact.")
    otp = b._make_test_otp(int(inst["id"]), int(contact["id"]))
    return {"status": "success", "organisation": company, "phone": phone, "test_code": otp}
