"""Admin API for B2B support tickets (created by the B2B assistant)."""
from fastapi import APIRouter, Body, Depends, HTTPException

from auth.admin_auth import require_admin

router = APIRouter()


@router.get("/admin/b2b/tickets")
def tickets(status: str = "", admin: str = Depends(require_admin)):
    from auth import b2b_assist
    try:
        return {"status": "success", "tickets": b2b_assist.list_tickets(status)}
    except Exception as e:
        raise HTTPException(status_code=500, detail="Could not read tickets: " + type(e).__name__)


@router.post("/admin/b2b/tickets/{ticket_no}/status")
def ticket_status(ticket_no: str, body: dict = Body(...), admin: str = Depends(require_admin)):
    from auth import b2b_assist
    try:
        b2b_assist.set_ticket_status(ticket_no, str(body.get("status") or ""), str(body.get("note") or ""), str(admin))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail="Could not update the ticket: " + type(e).__name__)
    return {"status": "success"}
