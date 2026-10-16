"""Admin API for Scheduled Reports (Admin panel > Settings > Scheduled Reports). All routes need an admin session."""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from auth.admin_auth import require_admin

router = APIRouter()


def _aud(admin, action, target=""):
    try:
        from agent.guard_hooks import _audit
        _audit(admin, action, target)
    except Exception:
        pass


class ScheduleIn(BaseModel):
    client: str
    channels: List[str] = []
    email_to: Optional[List[str] | str] = None
    whatsapp_to: Optional[List[str] | str] = None
    sections: List[str] = []
    frequency: str = "daily"
    send_time: str = "08:00"
    weekday: int = 0
    month_day: int = 1


def _clients():
    from database.license_db import get_conn
    c = get_conn()
    try:
        rows = c.execute("SELECT name, client_prefix FROM institutions WHERE client_prefix IS NOT NULL AND client_prefix <> ''").fetchall()
    finally:
        c.close()
    out = []
    for r in rows:
        d = dict(r.items()) if hasattr(r, "items") else dict(r)
        out.append({"code": str(d["client_prefix"]).upper(), "name": d.get("name") or d["client_prefix"]})
    return sorted(out, key=lambda x: x["name"].lower())


def _hospital(code):
    for c in _clients():
        if c["code"] == code:
            return c["name"]
    return None


@router.get("/admin/report-schedules")
def list_all(admin: str = Depends(require_admin)):
    from reports import scheduled_reports as sr
    from notifications import mailer, whatsapp
    rows = sr.list_schedules()
    for r in rows:
        r["runs"] = sr.recent_runs(r["id"], 5)
    return {"status": "success", "schedules": rows, "clients": _clients(),
            "sections": [{"key": k, "label": v[0]} for k, v in sr.SECTIONS.items()],
            "channels_ready": {"email": mailer.configured(), "whatsapp": whatsapp.configured()},
            "tz_minutes": sr.TZ_MIN}


@router.post("/admin/report-schedules")
def create(body: ScheduleIn, admin: str = Depends(require_admin)):
    from reports import scheduled_reports as sr
    clean, err = sr.validate(body.model_dump() if hasattr(body, "model_dump") else body.dict())
    if err:
        return {"status": "error", "message": err}
    name = _hospital(clean["client"])
    if not name:
        return {"status": "error", "message": "That client was not found."}
    _aud(admin, "Created scheduled report", str(name))
    return {"status": "success", "schedule": sr.save_schedule(clean, name, str(admin))}


@router.put("/admin/report-schedules/{sid}")
def update(sid: int, body: ScheduleIn, admin: str = Depends(require_admin)):
    from reports import scheduled_reports as sr
    if not sr.get_schedule(sid):
        raise HTTPException(status_code=404, detail="Schedule not found.")
    clean, err = sr.validate(body.model_dump() if hasattr(body, "model_dump") else body.dict())
    if err:
        return {"status": "error", "message": err}
    name = _hospital(clean["client"])
    if not name:
        return {"status": "error", "message": "That client was not found."}
    _aud(admin, "Edited scheduled report", "#%s %s" % (sid, name))
    return {"status": "success", "schedule": sr.save_schedule(clean, name, str(admin), sid=sid)}


@router.delete("/admin/report-schedules/{sid}")
def remove(sid: int, admin: str = Depends(require_admin)):
    from reports import scheduled_reports as sr
    sr.delete_schedule(sid)
    _aud(admin, "Deleted scheduled report", "#%s" % sid)
    return {"status": "success"}


@router.post("/admin/report-schedules/{sid}/toggle")
def toggle(sid: int, admin: str = Depends(require_admin)):
    from reports import scheduled_reports as sr
    s = sr.get_schedule(sid)
    if not s:
        raise HTTPException(status_code=404, detail="Schedule not found.")
    return {"status": "success", "schedule": sr.set_enabled(sid, not s["enabled"])}


@router.post("/admin/report-schedules/{sid}/preview")
def preview(sid: int, admin: str = Depends(require_admin)):
    """Builds the report now and returns the text. Sends NOTHING."""
    from reports import scheduled_reports as sr
    r = sr.run_schedule(sid, manual=True, dry=True)
    return {"status": "success" if r["ok"] else "error", "message": r["detail"], "text": r["text"]}


@router.post("/admin/report-schedules/{sid}/run-now")
def run_now(sid: int, admin: str = Depends(require_admin)):
    """Builds and SENDS the report now to the saved recipients."""
    from reports import scheduled_reports as sr
    r = sr.run_schedule(sid, manual=True)
    return {"status": "success" if r["ok"] else "error", "message": r["detail"]}
