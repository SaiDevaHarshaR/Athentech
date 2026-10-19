"""Admin: edit and delete B2B contacts (people). Organisations themselves live in the client's LIS (mstOrganisation) and are managed in Sahasra."""
import re
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from auth.admin_auth import require_admin

router = APIRouter()


class ContactEdit(BaseModel):
    institution_id: int = Field(gt=0)
    organisation_code: str = Field(min_length=1, max_length=80)
    contact_name: str = Field(min_length=1, max_length=120)
    phone: str = Field(min_length=8, max_length=30)


@router.put("/admin/b2b/contacts/{contact_id}")
def edit_contact(contact_id: int, body: ContactEdit, admin: str = Depends(require_admin)):
    from auth import b2b_portal as b
    inst = b._institution_by_id(body.institution_id)
    if not inst:
        raise HTTPException(404, "Institution not found")
    code = body.organisation_code.strip().upper()
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", code):
        raise HTTPException(400, "Invalid organisation code.")
    company = b._org_name(inst, code)
    if not company:
        raise HTTPException(422, "Organisation code does not exist in this client's LIS database.")
    phone = b._phone(body.phone)
    conn = b._admin_conn()
    try:
        cur = conn.cursor()
        old = cur.execute("SELECT phone_e164, organisation_code FROM dbo.sahasra_b2b_contacts WHERE id=? AND institution_id=?",
                          (contact_id, body.institution_id)).fetchone()
        if not old:
            raise HTTPException(404, "Contact not found")
        try:
            cur.execute("UPDATE dbo.sahasra_b2b_contacts SET organisation_code=?, contact_name=?, phone_e164=? WHERE id=? AND institution_id=?",
                        (code, body.contact_name.strip(), phone, contact_id, body.institution_id))
        except Exception:
            conn.rollback()
            raise HTTPException(409, "That mobile number is already registered for this client.")
        if str(old[0]) != phone or str(old[1]) != code:      # identity changed: old sessions must not survive
            cur.execute("UPDATE dbo.sahasra_b2b_sessions SET revoked=1 WHERE contact_id=? AND institution_id=?", (contact_id, body.institution_id))
        conn.commit()
    except HTTPException:
        raise
    except Exception:
        try: conn.rollback()
        except Exception: pass
        raise HTTPException(500, "Could not update the contact.")
    finally:
        conn.close()
    return {"status": "success", "organisation": company, "phone": phone}


@router.delete("/admin/b2b/contacts/{contact_id}")
def delete_contact(contact_id: int, institution_id: int = Query(..., gt=0), admin: str = Depends(require_admin)):
    from auth import b2b_portal as b
    conn = b._admin_conn()
    try:
        cur = conn.cursor()
        cur.execute("UPDATE dbo.sahasra_b2b_sessions SET revoked=1 WHERE contact_id=? AND institution_id=?", (contact_id, institution_id))
        cur.execute("DELETE FROM dbo.sahasra_b2b_test_otp WHERE contact_id=? AND institution_id=?", (contact_id, institution_id))
        cur.execute("DELETE FROM dbo.sahasra_b2b_contacts WHERE id=? AND institution_id=?", (contact_id, institution_id))
        if cur.rowcount != 1:
            conn.rollback()
            raise HTTPException(404, "Contact not found")
        conn.commit()
    except HTTPException:
        raise
    except Exception:
        try: conn.rollback()
        except Exception: pass
        raise HTTPException(500, "Could not delete the contact.")
    finally:
        conn.close()
    return {"status": "success"}
