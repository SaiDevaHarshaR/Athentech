import time

from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel
from typing import List, Optional

from agent.agent import ask_agent
from langchain_core.messages import HumanMessage, AIMessage

from auth.license_service import (
    create_license,
    validate_license,
    list_licenses,
    revoke_license,
    list_institutions,
    create_institution,
    update_institution,
    set_license_status,
    get_role_permissions,
    update_role_permissions,
    get_settings,
    update_settings,
)
from auth.admin_auth import require_admin, create_admin_token, check_admin_credentials
from auth.admin_service import list_admins, create_admin, set_admin_status, change_admin_password
from audit.log import audit, read_audit_log
from reports.pdf_generator import generate_smart_report
from reports.patient_report_generator import build_patient_report_data, PatientNotFound, PatientAmbiguous
from database.license_db import init_license_db, seed_demo_institutions, seed_bootstrap_admin
from notifications.email import send_alert_email
from notifications.webhook import send_webhook_alert
from notifications.expiry_checker import start_background_expiry_checker, check_and_alert
from config import settings

app = FastAPI(title="Sahasra AI Agent")

WINDOW = 60  # seconds — rate limit window; the limit itself is now read from settings (was a hardcoded constant)
RATE = {}

init_license_db()
seed_demo_institutions()
seed_bootstrap_admin()  # one-time migration: legacy .env admin -> real admins table, see auth/admin_service.py
start_background_expiry_checker()  # actually fires the "email alerts for expiring licenses" setting

# CORS: restrict to known origins (set ALLOWED_ORIGINS in .env), not "*".
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def security_middleware(request: Request, call_next):
    # Rate limit — reads the current admin-configured limit on every
    # request. A tiny SQLite read; fine at this scale, revisit if traffic
    # ever justifies caching it in memory with a short TTL.
    try:
        limit = get_settings()["rate_limit_per_minute"]
    except Exception:
        limit = 300  # settings DB unreachable — fail open with the old default rather than hard-blocking everything

    ip = request.client.host if request.client else "unknown"
    now = time.time()
    hits = [t for t in RATE.get(ip, []) if now - t < WINDOW]
    if len(hits) >= limit:
        return JSONResponse(status_code=429, content={"detail": "Too many requests"})
    hits.append(now)
    RATE[ip] = hits

    response = await call_next(request)

    # Security headers
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store"

    return response


def _log_admin_action(admin: str, action: str, target: str = "", meta: dict = None):
    """
    Real per-admin accountability: every mutating admin action gets
    logged with the actual authenticated admin's username, not just a
    generic 'Admin' label. Visible in /admin/audit and the Audit Logs
    page alongside the existing premium_query / invalid_code_attempt
    events.
    """
    audit(event="admin_action", role=None, code=None, question=f"{action}: {target}",
          meta={"actor": admin, "action": action, "target": target, **(meta or {})})


# ---------- Request/response models ----------

class RolePermissionUpdate(BaseModel):
    role: str
    tables: list[str]


class LicenseStatusRequest(BaseModel):
    code: str
    status: str  # Active / Suspended / Revoked


class InstitutionCreateRequest(BaseModel):
    name: str
    client_prefix: str
    db_name: str
    type: str = "Hospital"
    city: str = ""
    status: str = "Active"


class InstitutionUpdateRequest(BaseModel):
    name: Optional[str] = None
    client_prefix: Optional[str] = None
    db_name: Optional[str] = None
    type: Optional[str] = None
    city: Optional[str] = None
    status: Optional[str] = None


class Message(BaseModel):
    role: str
    content: str


class QueryRequest(BaseModel):
    question: str
    activation_code: Optional[str] = None
    chat_history: Optional[List[Message]] = []


class GenerateLicenseRequest(BaseModel):
    institution_id: int
    role: str
    phone: str
    dob_year: str
    plan: str = "Standard"
    valid_days: Optional[int] = None  # falls back to the admin-configured default if not given


class ValidateLicenseRequest(BaseModel):
    code: str


class RevokeLicenseRequest(BaseModel):
    code: str


class PDFRequest(BaseModel):
    title: str = "Sahasra AI Report"
    hospital_name: str = "Hospital"
    role: str = "Staff"
    activation_code: str = ""
    content_lines: list[str] = []


class PatientReportRequest(BaseModel):
    patient_identifier: str  # UHID or name
    activation_code: str


class AdminLoginRequest(BaseModel):
    username: str
    password: str


class AdminCreateRequest(BaseModel):
    username: str
    password: str
    display_name: str = ""


class AdminStatusRequest(BaseModel):
    status: str  # Active / Inactive


class AdminPasswordRequest(BaseModel):
    new_password: str


class SettingsUpdateRequest(BaseModel):
    license_validity_days: Optional[int] = None
    normal_mode_enabled: Optional[bool] = None
    rate_limit_per_minute: Optional[int] = None
    extra_blocked_patterns: Optional[List[str]] = None
    output_redaction_enabled: Optional[bool] = None
    email_alerts_enabled: Optional[bool] = None
    webhook_url: Optional[str] = None
    smtp_host: Optional[str] = None
    smtp_port: Optional[int] = None
    smtp_user: Optional[str] = None
    smtp_password: Optional[str] = None
    alert_email_to: Optional[str] = None


# ---------- Public ----------

@app.get("/")
def home():
    return {"message": "Sahasra AI Agent is running"}


# ---------- Admin auth ----------

@app.post("/admin/login")
def api_admin_login(req: AdminLoginRequest):
    try:
        ok = check_admin_credentials(req.username, req.password)
    except RuntimeError as e:
        # No admin accounts exist yet — see auth/admin_auth.py for the bootstrap flow.
        raise HTTPException(status_code=500, detail=str(e))

    if not ok:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_admin_token(req.username)
    audit(event="admin_login", role=None, code=None, question=None, meta={"actor": req.username})
    return {"status": "success", "token": token}


# ---------- Admin: user accounts (auth required) ----------
# Real multi-admin accounts, replacing the single shared login — see
# auth/admin_service.py. Any logged-in admin can manage other admins;
# there's no role hierarchy (super-admin vs regular) yet.

@app.get("/admin/users")
def api_list_admin_users(admin: str = Depends(require_admin)):
    return {"status": "success", "admins": list_admins()}


@app.post("/admin/users")
def api_create_admin_user(req: AdminCreateRequest, admin: str = Depends(require_admin)):
    try:
        data = create_admin(req.username, req.password, req.display_name)
        _log_admin_action(admin, "Created admin account", req.username)
        return {"status": "success", "admin": data}
    except ValueError as e:
        return {"status": "error", "message": str(e)}


@app.post("/admin/users/{username}/status")
def api_set_admin_status(username: str, req: AdminStatusRequest, admin: str = Depends(require_admin)):
    try:
        ok = set_admin_status(username, req.status)
    except ValueError as e:
        return {"status": "error", "message": str(e)}
    if not ok:
        return {"status": "error", "message": "Admin not found"}
    _log_admin_action(admin, f"Set admin status to {req.status}", username)
    return {"status": "success"}


@app.post("/admin/users/{username}/password")
def api_change_admin_password(username: str, req: AdminPasswordRequest, admin: str = Depends(require_admin)):
    try:
        ok = change_admin_password(username, req.new_password)
    except ValueError as e:
        return {"status": "error", "message": str(e)}
    if not ok:
        return {"status": "error", "message": "Admin not found"}
    _log_admin_action(admin, "Changed admin password", username)
    return {"status": "success"}


# ---------- Admin: institutions (auth required) ----------

@app.get("/admin/institutions")
def api_list_institutions(admin: str = Depends(require_admin)):
    return {"status": "success", "institutions": list_institutions()}


@app.post("/admin/institutions")
def api_create_institution(req: InstitutionCreateRequest, admin: str = Depends(require_admin)):
    try:
        data = create_institution(
            name=req.name,
            client_prefix=req.client_prefix,
            db_name=req.db_name,
            type_=req.type,
            city=req.city,
            status=req.status,
        )
        _log_admin_action(admin, "Created institution", req.name)
        return {"status": "success", "institution": data}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.patch("/admin/institutions/{institution_id}")
def api_update_institution(institution_id: int, req: InstitutionUpdateRequest, admin: str = Depends(require_admin)):
    try:
        data = update_institution(institution_id, **req.model_dump(exclude_unset=True))
        _log_admin_action(admin, "Updated institution", data.get("name", str(institution_id)),
                           meta={"changes": req.model_dump(exclude_unset=True)})
        return {"status": "success", "institution": data}
    except ValueError as e:
        return {"status": "error", "message": str(e)}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ---------- Admin: licenses (auth required) ----------

@app.get("/admin/licenses")
def api_list_licenses(admin: str = Depends(require_admin)):
    return {"status": "success", "licenses": list_licenses()}


@app.post("/admin/licenses/generate")
def api_generate_license(req: GenerateLicenseRequest, admin: str = Depends(require_admin)):
    try:
        valid_days = req.valid_days
        if valid_days is None:
            valid_days = get_settings()["license_validity_days"]

        data = create_license(
            institution_id=req.institution_id,
            role=req.role,
            phone=req.phone,
            dob_year=req.dob_year,
            plan=req.plan,
            valid_days=valid_days,
            created_by=admin,  # real admin username, not the old hardcoded "admin" literal
        )
        _log_admin_action(admin, "Generated license", data.get("code", ""))
        return {"status": "success", "license": data}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.post("/admin/licenses/status")
def api_set_license_status(req: LicenseStatusRequest, admin: str = Depends(require_admin)):
    ok = set_license_status(req.code, req.status)
    if not ok:
        return {"status": "error", "message": "License not found"}
    _log_admin_action(admin, f"Set license status to {req.status}", req.code)
    return {"status": "success", "message": f"License marked {req.status}"}


@app.post("/admin/licenses/revoke")
def api_revoke_license(req: RevokeLicenseRequest, admin: str = Depends(require_admin)):
    ok = revoke_license(req.code)
    if not ok:
        return {"status": "error", "message": "Code not found"}
    _log_admin_action(admin, "Revoked license", req.code)
    return {"status": "success", "message": "License revoked"}


# ---------- Admin: roles (auth required) ----------

@app.get("/admin/roles")
def api_get_roles(admin: str = Depends(require_admin)):
    return {"status": "success", "roles": get_role_permissions()}


@app.put("/admin/roles")
def api_update_role(req: RolePermissionUpdate, admin: str = Depends(require_admin)):
    update_role_permissions(req.role, req.tables)
    _log_admin_action(admin, "Updated role permissions", req.role, meta={"tables": req.tables})
    return {"status": "success"}


# ---------- Admin: settings (auth required) ----------

@app.get("/admin/settings")
def api_get_settings(admin: str = Depends(require_admin)):
    return {"status": "success", "settings": get_settings()}


@app.put("/admin/settings")
def api_update_settings(req: SettingsUpdateRequest, admin: str = Depends(require_admin)):
    changed_fields = req.model_dump(exclude_unset=True)
    updated = update_settings(**changed_fields)
    # Don't log secret values (smtp_password) into the audit trail.
    safe_changes = {k: v for k, v in changed_fields.items() if k != "smtp_password"}
    _log_admin_action(admin, "Updated settings", "", meta={"changes": safe_changes})
    return {"status": "success", "settings": updated}


# ---------- Admin: notifications (auth required) ----------
# Makes the email/webhook settings actually do something you can verify
# right now, instead of wondering whether they're wired up at all.

@app.post("/admin/notifications/test")
def api_test_notifications(admin: str = Depends(require_admin)):
    email_ok, email_msg = send_alert_email(
        "Sahasra AI: Test Alert",
        f"This is a test alert triggered manually by {admin} from the admin panel."
    )
    webhook_ok, webhook_msg = send_webhook_alert("test_alert", {"triggered_by": admin})

    _log_admin_action(admin, "Sent test notification", "",
                       meta={"email_ok": email_ok, "webhook_ok": webhook_ok})

    return {
        "status": "success",
        "email": {"success": email_ok, "message": email_msg},
        "webhook": {"success": webhook_ok, "message": webhook_msg},
    }


@app.post("/admin/notifications/check-expiring")
def api_check_expiring_licenses(admin: str = Depends(require_admin)):
    """Manually trigger the same expiry check the background job runs daily — useful to verify it actually works without waiting a day."""
    result = check_and_alert()
    return {"status": "success", "result": result}


# ---------- Admin: audit log (auth required) ----------
# Real compliance data — every premium query, invalid activation attempt,
# and now every admin action (who created/edited/revoked what), read
# straight from audit/audit.log.

@app.get("/admin/audit")
def api_get_audit(limit: int = 500, admin: str = Depends(require_admin)):
    return {"status": "success", "events": read_audit_log(limit=limit)}


# ---------- Admin utility: raw code validation (auth required) ----------
# Not used by the public chat widget (which validates via /ask with
# question="validate"). Gated because an unauthenticated version of this
# is a ready-made oracle for brute-forcing activation codes.

@app.post("/licenses/validate")
def api_validate_license(req: ValidateLicenseRequest, admin: str = Depends(require_admin)):
    result = validate_license(req.code)
    if not result.get("valid"):
        return {"status": "error", "message": result.get("reason", "invalid")}
    return {"status": "success", "license": result}


# ---------- Reports ----------

@app.post("/generate-pdf")
async def generate_pdf(req: PDFRequest):
    data = {
        "report_title": req.title,
        "hospital_name": req.hospital_name,
        "user_role": req.role,
        "activation_code": req.activation_code,
        "content_lines": req.content_lines,
    }

    # generate_smart_report uses Playwright's sync API (launches a real
    # browser to render) — that's a ~0.7s blocking call. Running it
    # directly here would freeze the whole async event loop for that
    # long on every PDF request, stalling any other concurrent request
    # (chat, admin panel, everything) for the duration. run_in_executor
    # runs it in a background thread instead, so only this one request
    # waits on it.
    import asyncio
    loop = asyncio.get_event_loop()
    pdf_file = await loop.run_in_executor(None, generate_smart_report, data)

    return StreamingResponse(
        pdf_file,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=sahasra_report.pdf"},
    )


@app.post("/generate-patient-report")
async def generate_patient_report(req: PatientReportRequest):
    """
    The REAL Smart Report — looks up one specific real patient and
    builds their report from freshly-queried real data, instead of
    just re-wrapping whatever the last chat answer happened to say.
    """
    validation = validate_license(req.activation_code)
    if not validation.get("valid"):
        raise HTTPException(status_code=401, detail="Invalid or expired activation code.")

    role = validation.get("role", "viewer")
    db_name = validation.get("db_name")
    hospital_name = validation.get("hospital_name", "Hospital")

    from agent.agent import llm as agent_llm

    import asyncio
    loop = asyncio.get_event_loop()

    try:
        report_data = await loop.run_in_executor(
            None, build_patient_report_data, req.patient_identifier, db_name, role, hospital_name, agent_llm
        )
    except PatientNotFound:
        raise HTTPException(status_code=404, detail=f"No patient found matching '{req.patient_identifier}'.")
    except PatientAmbiguous as e:
        names = ", ".join(f"{c['name']} (UHID: {c['uhid']})" for c in e.candidates[:5])
        raise HTTPException(
            status_code=409,
            detail=f"Multiple matching patients found: {names}. Please specify the UHID instead."
        )
    except ConnectionError as e:
        raise HTTPException(status_code=503, detail=str(e))

    pdf_file = await loop.run_in_executor(None, generate_smart_report, report_data)

    return StreamingResponse(
        pdf_file,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=patient_report.pdf"},
    )


# ---------- Public: ask ----------

@app.post("/ask")
async def ask_question(req: QueryRequest):
    try:
        history = []
        for msg in req.chat_history or []:
            if msg.role == "user":
                history.append(HumanMessage(content=msg.content))
            else:
                history.append(AIMessage(content=msg.content))

        is_premium = False
        role = "viewer"
        db_name = "hospital_demo"
        hospital_name = "Demo Hospital"

        if req.activation_code:
            validation = validate_license(req.activation_code)
            if validation.get("valid"):
                is_premium = True
                role = validation.get("role", "viewer")
                db_name = validation.get("db_name", "hospital_demo")
                hospital_name = validation.get("hospital_name", "Hospital")
            else:
                # Real failure event — previously invalid attempts were
                # never recorded anywhere, so the admin panel's "failed
                # validation" analytics had nothing real to show.
                audit(
                    event="invalid_code_attempt",
                    role=None,
                    code=req.activation_code,
                    question=None,
                    meta={"reason": validation.get("reason", "invalid")},
                )
                return {
                    "status": "error",
                    "answer": "Invalid or expired activation code.",
                }

        if not is_premium and not get_settings()["normal_mode_enabled"]:
            return {
                "status": "error",
                "answer": "General-knowledge mode is currently disabled. Please enter a hospital activation code to continue.",
            }

        is_validate_ping = req.question.strip().lower() == "validate"

        if is_premium and not is_validate_ping:
            audit(
                event="premium_query",
                role=role,
                code=req.activation_code,
                question=req.question,
                meta={"db_name": db_name, "hospital": hospital_name},
            )

        # Fast-path: the widget sends question="validate" right after the
        # user enters an activation code, just to confirm it worked and
        # learn the role/hospital name. No need to invoke the LLM for that.
        if is_validate_ping:
            return {
                "status": "success",
                "answer": "Code validated" if is_premium else "Invalid or expired activation code.",
                "mode": "premium" if is_premium else "normal",
                "role": role if is_premium else None,
                "hospital_name": hospital_name if is_premium else None,
            }

        answer = ask_agent(
            question=req.question,
            db_name=db_name,
            chat_history=history,
            is_premium=is_premium,
            role=role,
            hospital_name=hospital_name,
        )

        return {
            "status": "success",
            "answer": answer,
            "mode": "premium" if is_premium else "normal",
            "role": role if is_premium else None,
            "hospital_name": hospital_name if is_premium else None,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))