import time
from datetime import datetime
import database.connection as _dbconn
from agent import guardian
guardian.install(_dbconn)   # must run before other modules import get_hospital_connection
#from reports.excel_export import export_all_branches_collection
from reports.excel_export import run_excel_export
from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel
from typing import List, Optional
from agent.agent import ask_agent
from agent.followups import suggest_followups
from agent.chip_health import verified_chips, build_router as build_chip_router
from langchain_core.messages import HumanMessage, AIMessage
from database.connection import get_hospital_connection
from auth.license_service import (
    create_license,
    validate_license,
    list_licenses,
    revoke_license,
    delete_license,
    update_license,
    list_institutions,
    create_institution,
    update_institution,
    delete_institution,
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
from database.license_db import init_license_db
try:
    from database.license_db import seed_demo_institutions
except ImportError:                       # older/newer license_db without demo seeding: skip it, don't crash
    def seed_demo_institutions():
        print('[startup] WARNING: seed_demo_institutions missing in database/license_db.py - demo seeding skipped', flush=True)
try:
    from database.license_db import seed_bootstrap_admin
except ImportError:
    def seed_bootstrap_admin():
        print('[startup] WARNING: seed_bootstrap_admin missing in database/license_db.py - legacy admin migration skipped (existing admins unaffected)', flush=True)
from database.byok_migration import ensure_llm_columns
import database.byok_migration as _byok_mig
from notifications.email import send_alert_email
from notifications.webhook import send_webhook_alert
from notifications.expiry_checker import start_background_expiry_checker, check_and_alert
from config import settings
from auth.usage_limiter import check_budget, record_usage
import sys
import io
import os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
from observability.metrics import metrics_middleware
from observability.ops_summary import summary as ops_summary
app = FastAPI(title="Sahasra AI Agent")
app.middleware("http")(metrics_middleware)
#print(f"[DEBUG] Loaded ALLOWED_ORIGINS: {settings.allowed_origins_list}")
# CORS: restrict to known origins (set ALLOWED_ORIGINS in .env), not "*".
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class RolePermissionsRequest(BaseModel):
    role: str
    tables: list[str]


@app.post("/admin/roles")
def api_set_role_permissions(req: RolePermissionsRequest, admin: str = Depends(require_admin)):
    from auth.license_service import set_role_permissions
    data = set_role_permissions(req.role, req.tables)
    _log_admin_action(admin, "Updated role permissions", req.role, meta={"tables": req.tables})
    return {"status": "success", "role": data}


@app.delete("/admin/roles/{role}")
def api_delete_role_permissions(role: str, admin: str = Depends(require_admin)):
    from auth.license_service import delete_role_permissions
    ok = delete_role_permissions(role)
    if not ok:
        return {"status": "error", "message": "Role not found"}
    _log_admin_action(admin, "Deleted role permissions", role)
    return {"status": "success"}

@app.middleware("http")
async def security_middleware(request: Request, call_next):
    if request.method == "OPTIONS":
        return await call_next(request)

    origin = request.headers.get("origin")
    def _with_cors(response):
        if origin and origin in settings.allowed_origins_list:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Credentials"] = "true"
        return response

    try:
        limit = get_settings()["rate_limit_per_minute"]
    except Exception:
        limit = 300

    ip = request.client.host if request.client else "unknown"
    now = time.time()
    hits = [t for t in RATE.get(ip, []) if now - t < WINDOW]
    if len(hits) >= limit:
        return _with_cors(JSONResponse(status_code=429, content={"detail": "Too many requests"}))
    hits.append(now)
    RATE[ip] = hits

    response = await call_next(request)

    # Security headers
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store"

    return response


WINDOW = 60  # seconds — rate limit window; the limit itself is now read from settings (was a hardcoded constant)
RATE = {}
# Separate from the per-IP RATE above: many real users can share one IP
# (NAT, a hospital's shared network), so a pure per-IP limit means one
# busy hospital can eat the shared budget for everyone else on the same
# network. This tracks usage per ACTIVATION CODE instead — a hospital's
# heavy legitimate usage only affects that hospital's own limit.
CODE_RATE = {}

init_license_db()
ensure_llm_columns()                     # never raises; sets byok_migration.READY and logs a loud ERROR when it fails
seed_demo_institutions()
seed_bootstrap_admin()  # one-time migration: legacy .env admin -> real admins table, see auth/admin_service.py
start_background_expiry_checker()  # actually fires the "email alerts for expiring licenses" setting


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

from fastapi.staticfiles import StaticFiles

app.mount("/widget", StaticFiles(directory="widget_files", html=True), name="widget")
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
    db_server: str | None = None
    db_user: str | None = None
    db_password: str | None = None    
    type: str = "Hospital"
    city: str = ""
    status: str = "Active"
    llm_provider: str | None = None
    llm_model: str | None = None
    llm_api_key: str | None = None
    llm_base_url: str | None = None
    allow_athentech_fallback: bool = False



class InstitutionUpdateRequest(BaseModel):
    name: Optional[str] = None
    client_prefix: Optional[str] = None
    db_name: Optional[str] = None
    db_server: Optional[str] = None
    db_user: Optional[str] = None
    db_password: Optional[str] = None
    type: Optional[str] = None
    city: Optional[str] = None
    status: Optional[str] = None
    llm_provider: Optional[str] = None
    llm_model: Optional[str] = None
    llm_api_key: Optional[str] = None
    llm_base_url: Optional[str] = None
    remove_llm_key: Optional[bool] = None
    allow_athentech_fallback: Optional[bool] = None



class Message(BaseModel):
    role: str
    content: str


class QueryRequest(BaseModel):
    question: str
    activation_code: Optional[str] = None
    chat_history: Optional[List[Message]] = []
    device_fingerprint: Optional[str] = None
    client: Optional[str] = None


class GenerateLicenseRequest(BaseModel):
    institution_id: int
    role: str
    phone: str
    dob_year: str
    email: Optional[str] = None
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
    client: Optional[str] = None


class PatientReportRequest(BaseModel):
    patient_identifier: str 
    client: Optional[str] = None # UHID or name
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
    otp_smtp_host: Optional[str] = None
    otp_smtp_port: Optional[int] = None
    llm_custom_providers: Optional[list] = None
    otp_smtp_user: Optional[str] = None
    otp_smtp_password: Optional[str] = None
    alert_smtp_host: Optional[str] = None
    alert_smtp_port: Optional[int] = None
    alert_smtp_user: Optional[str] = None
    alert_smtp_password: Optional[str] = None
    alert_email_to: Optional[str] = None
    openai_token_budget: Optional[int] = None
    openai_token_baseline: Optional[int] = None
    widget_title: Optional[str] = None
    widget_subtitle: Optional[str] = None
    widget_welcome_message: Optional[str] = None
    widget_primary_color: Optional[str] = None
    widget_secondary_color: Optional[str] = None
    widget_bg_color: Optional[str] = None
    widget_width_px: Optional[int] = None
    llm_provider_order: Optional[list] = None
    llm_groq_key_override: Optional[str] = None
    llm_gemini_key_override: Optional[str] = None
    llm_mistral_key_override: Optional[str] = None
    llm_cohere_key_override: Optional[str] = None
    llm_openrouter_key_override: Optional[str] = None
    llm_openai_key_override: Optional[str] = None
    widget_height_px: Optional[int] = None
    widget_icon_url: Optional[str] = None
    widget_disclaimer_text: Optional[str] = None
    widget_footer_text: Optional[str] = None
    widget_role_suggestions: Optional[dict] = None
    widget_max_history: Optional[int] = None
    widget_session_timeout_min: Optional[int] = None
    widget_preview_toast_enabled: Optional[bool] = None
    widget_escalate_phone: Optional[str] = None
    widget_escalate_message: Optional[str] = None
    widget_idle_nudge_enabled: Optional[bool] = None
    widget_idle_nudge_minutes: Optional[int] = None
    widget_idle_nudge_message: Optional[str] = None

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


# Guardian support console is hosted by the existing API, not a separate service.
@app.get("/admin/guardian/console", include_in_schema=False)
def guardian_console():
    from fastapi.responses import FileResponse
    return FileResponse(os.path.join(os.path.dirname(__file__), "guardian_console.html"), media_type="text/html", headers={"Cache-Control": "no-store"})

@app.get("/admin/guardian/support-report")
def guardian_support_report(admin: str = Depends(require_admin)):
    from agent.guardian_support import diagnostic_report
    return diagnostic_report(guardian.status())

@app.get("/admin/guardian/schema-check/{code}")
def guardian_schema_check(code: str, admin: str = Depends(require_admin)):
    """Metadata-only inspection; first successful inspection stores a comparison baseline."""
    from agent.guardian_support import inspect_columns, compare_snapshot
    v = validate_license(code)
    if not v.get("valid"):
        raise HTTPException(status_code=404, detail="Unknown or invalid activation code")
    db = v.get("db_name")
    conn = None
    try:
        conn = get_hospital_connection(db, v.get("db_server"), v.get("db_user"), v.get("db_password"))
        if conn is None:
            raise HTTPException(status_code=502, detail="Database unavailable")
        changes = compare_snapshot(db, inspect_columns(conn), save=False)
        if not changes["baseline_exists"]:
            changes = compare_snapshot(db, inspect_columns(conn), save=True)
        return {"status":"success","database":db,"schema":changes,
                "message":"Schema changes need DBA review; no client database objects were modified."}
    except HTTPException:
        raise
    except Exception as e:
        ev=guardian.record_event(db,"selfcheck",str(e))
        raise HTTPException(status_code=502,detail=ev["message"])
    finally:
        if conn is not None:
            try: conn.close()
            except Exception: pass


@app.get("/admin/guardian/status")
def api_guardian_status(admin: str = Depends(require_admin)):
    """Clients with recent errors, plain-language cause and safe action; open circuit breakers."""
    return {"status": "success", **guardian.status()}


@app.get("/admin/guardian/selfcheck/{code}")
def api_guardian_selfcheck(code: str, admin: str = Depends(require_admin)):
    """Read-only health check of ONE client: connect, schema profile, sample query. Plain-language result."""
    from agent import schema_ctx
    v = validate_license(code)
    if not v.get("valid"):
        raise HTTPException(status_code=404, detail="Unknown or invalid activation code.")
    db = v.get("db_name")
    checks = []
    def add(name, ok, detail=""):
        checks.append({"check": name, "ok": bool(ok), "detail": guardian._clean(detail, 200)})
    conn = None
    try:
        conn = get_hospital_connection(db, v.get("db_server"), v.get("db_user"), v.get("db_password"))
        add("Database connection", conn is not None, "" if conn else "Could not connect")
        if conn:
            p = schema_ctx.get_profile(conn, db, v.get("db_server"))
            caps = schema_ctx.capabilities(p)
            add("Schema profile", True, f"metric={p.get('coll_metric')} ({caps.get('collection_metric_source')})")
            add("Collections table readable", caps["collections"])
            add("Config pins valid", not caps["config_rejected"], str(caps["config_rejected"]))
            cur = conn.cursor()
            cur.execute("SELECT TOP 1 1 FROM trnINVLABPRI")
            add("Bills table readable", cur.fetchone() is not None)
    except Exception as e:
        ev = guardian.record_event(db, "selfcheck", str(e))
        add("Self-check", False, ev["message"] + " " + ev["safe_action"])
    finally:
        try:
            if conn: conn.close()
        except Exception: pass
    return {"status": "success", "database": db, "healthy": all(c["ok"] for c in checks),
            "circuit_open": guardian.circuit_open(db), "checks": checks}


@app.get("/admin/client-diagnostics/{code}")
def api_client_diagnostics(code: str, refresh: bool = False, admin: str = Depends(require_admin)):
    """Per-client schema profile + capabilities (what the agent detected for this database)."""
    from agent import schema_ctx
    v = validate_license(code)
    if not v.get("valid"):
        raise HTTPException(status_code=404, detail="Unknown or invalid activation code.")
    conn = get_hospital_connection(v.get("db_name"), v.get("db_server"), v.get("db_user"), v.get("db_password"))
    if not conn:
        raise HTTPException(status_code=502, detail="Cannot connect to client database.")
    try:
        if refresh:
            schema_ctx.invalidate(v.get("db_name"), v.get("db_server"))
        p = schema_ctx.get_profile(conn, v.get("db_name"), v.get("db_server"))
        return {"status": "success", "database": v.get("db_name"),
                "capabilities": schema_ctx.capabilities(p), "profile": p}
    finally:
        try: conn.close()
        except Exception: pass


def _byok_not_ready():
    if _byok_mig.READY:
        return None
    return {"status": "error", "code": "byok_not_ready",
            "message": "AI-key storage is not ready (database migration failed: %s). Nothing was saved." % (_byok_mig.LAST_ERROR or "unknown")}


@app.get("/admin/llm-providers")
def api_llm_providers(admin: str = Depends(require_admin)):
    from agent import llm_providers
    return {"status": "success", "providers": llm_providers.CATALOG, "byok_ready": _byok_mig.READY, "byok_error": _byok_mig.LAST_ERROR}


@app.post("/admin/llm-providers/validate")
def api_llm_validate(req: dict, admin: str = Depends(require_admin)):
    """Test a key before saving. The key is not stored or logged."""
    from agent import llm_providers
    r = llm_providers.validate_key(req.get("provider"), req.get("api_key"), req.get("model"), req.get("base_url"))
    return {"status": "success" if r["ok"] else "error", **r}


# Multi-provider settings: separate from Institution editor and client LIS DB.
@app.get("/admin/institutions/{institution_id}/ai-providers")
def api_institution_ai_providers(institution_id: int, admin: str = Depends(require_admin)):
    if _byok_not_ready():
        return _byok_not_ready()
    from auth.institution_ai_slots import public_slots
    try:
        return {"status": "success", **public_slots(institution_id)}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception:
        raise HTTPException(status_code=503, detail="Institution AI settings are temporarily unavailable")


@app.put("/admin/institutions/{institution_id}/ai-providers")
def api_save_institution_ai_providers(institution_id: int, req: dict, admin: str = Depends(require_admin)):
    if _byok_not_ready():
        return _byok_not_ready()
    from auth.institution_ai_slots import save_slots
    from agent.llm_providers import validate_key
    try:
        result = save_slots(institution_id, req.get("slots"),
                            req.get("allow_athentech_fallback"), validate_key)
        _log_admin_action(admin, "Updated institution AI providers", str(institution_id),
                          meta={"provider_count": sum(1 for s in result["slots"] if s["enabled"] and s["has_key"]),
                                "athentech_fallback": result["allow_athentech_fallback"]})
        return {"status": "success", **result}
    except ValueError as e:
        return {"status": "error", "message": str(e)}
    except Exception as e:
        print(f"[byok] saving AI provider slots failed: {type(e).__name__}", flush=True)
        return {"status": "error", "message": "Could not save AI settings. Previous settings remain unchanged."}


@app.post("/admin/institutions/{institution_id}/ai-providers/{position}/revalidate")
def api_revalidate_institution_ai_slot(institution_id: int, position: int, admin: str = Depends(require_admin)):
    if _byok_not_ready():
        return _byok_not_ready()
    from auth.institution_ai_slots import revalidate_slot
    from agent.llm_providers import validate_key
    if not 1 <= position <= 25:
        raise HTTPException(status_code=400, detail="Invalid provider number")
    try:
        result = revalidate_slot(institution_id, position, validate_key)
        return {"status": "success" if result["ok"] else "error", **result}
    except ValueError as e:
        return {"status": "error", "message": str(e)}
    except Exception as e:
        print(f"[byok] slot revalidation failed: {type(e).__name__}", flush=True)
        return {"status": "error", "message": "Could not revalidate the saved provider"}


@app.post("/admin/institutions/{institution_id}/revalidate-llm-key")
def api_llm_revalidate(institution_id: int, admin: str = Depends(require_admin)):
    """Re-test the institution's SAVED key (e.g. after they say 'AI stopped working')."""
    from agent import llm_providers
    from database.license_db import get_conn
    conn = get_conn()
    try:
        row = conn.execute("SELECT client_prefix FROM institutions WHERE id = ?", (institution_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Institution not found")
        s = llm_providers.institution_llm_settings(row["client_prefix"])
        if not s:
            return {"status": "error", "code": "no_key", "message": "This institution has no AI key saved. Shared AthenTech AI requires explicit opt-in."}
        r = llm_providers.validate_key(s["provider"], s["api_key"], s["model"], s["base_url"])
        conn.execute("UPDATE institutions SET llm_key_status = ?, llm_key_checked_at = ? WHERE id = ?",
                     ("valid" if r["ok"] else r["code"], datetime.utcnow().isoformat(), institution_id))
        conn.commit()
        return {"status": "success" if r["ok"] else "error", **r}
    finally:
        conn.close()


@app.post("/admin/institutions")
def api_create_institution(req: InstitutionCreateRequest, admin: str = Depends(require_admin)):
    try:
        key_status = None
        # Institution inserts contain AI columns even if no key is supplied.
        # A failed admin-DB migration must be reported, never silently ignored.
        if _byok_not_ready():
            return _byok_not_ready()
        if req.llm_api_key:
            from agent import llm_providers
            chk = llm_providers.validate_key(req.llm_provider, req.llm_api_key, req.llm_model, req.llm_base_url)
            if not chk["ok"]:
                return {"status": "error", **chk}
            key_status = "valid"
        data = create_institution(
            name=req.name,
            client_prefix=req.client_prefix,
            db_name=req.db_name,
            db_server=req.db_server,
            db_user=req.db_user,
            db_password=req.db_password,            
            type_=req.type,
            city=req.city,
            status=req.status,
            llm_provider=req.llm_provider if req.llm_api_key else None,
            llm_model=req.llm_model if req.llm_api_key else None,
            llm_api_key=req.llm_api_key,
            llm_base_url=req.llm_base_url if req.llm_api_key else None,
            llm_key_status=key_status,
            allow_athentech_fallback=req.allow_athentech_fallback,
        )
        _log_admin_action(admin, "Created institution", req.name)
        return {"status": "success", "institution": data}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.patch("/admin/institutions/{institution_id}")
def api_update_institution(institution_id: int, req: InstitutionUpdateRequest, admin: str = Depends(require_admin)):
    try:
        changes = req.model_dump(exclude_unset=True)
        from agent import llm_providers
        # Legacy one-key writes must not silently conflict with multi-slot
        # configuration. Existing single-key institutions still work until
        # they are explicitly migrated by the AI Providers dialog.
        if any(k in changes for k in ("llm_provider", "llm_model", "llm_api_key", "llm_base_url", "remove_llm_key")):
            from database.license_db import get_conn
            _c = get_conn()
            try:
                _has = _c.execute("SELECT TOP 1 position FROM institution_ai_slots WHERE institution_id = ?",
                                  (institution_id,)).fetchone()
            finally:
                _c.close()
            if _has:
                return {"status": "error", "code": "use_ai_providers",
                        "message": "This institution uses multiple AI providers. Open its separate AI Providers dialog to edit keys."}
        if "allow_athentech_fallback" in changes and _byok_not_ready():
            return _byok_not_ready()
        if changes.pop("remove_llm_key", None):
            for k in ("llm_provider", "llm_model", "llm_api_key", "llm_base_url"):
                changes.pop(k, None)
            changes["clear_llm_key"] = True          # cleared inside the same UPDATE as the other edits
        elif changes.get("llm_api_key"):
            if _byok_not_ready():
                return _byok_not_ready()
            chk = llm_providers.validate_key(changes.get("llm_provider"), changes["llm_api_key"],
                                             changes.get("llm_model"), changes.get("llm_base_url"))
            if not chk["ok"]:
                return {"status": "error", **chk}
            changes["llm_key_status"] = "valid"
            changes["llm_key_checked_at"] = datetime.utcnow().isoformat()
        else:
            # provider/model edits without a new key are only allowed through re-validation of the saved key
            for k in ("llm_provider", "llm_model", "llm_base_url"):
                changes.pop(k, None)
        data = update_institution(institution_id, **changes)
        llm_providers.invalidate()
        # Don't log the raw db_password into the audit trail — same
        # reasoning as excluding smtp_password from the settings-update
        # audit log elsewhere: the audit log is meant to record WHAT
        # changed, not BE a place secrets end up in plaintext.
        safe_changes = {k: v for k, v in req.model_dump(exclude_unset=True).items() if k not in ("db_password", "llm_api_key")}
        if req.llm_api_key:
            safe_changes["llm_api_key"] = "[changed]"
        if "db_password" in req.model_dump(exclude_unset=True):
            safe_changes["db_password"] = "[changed]"
        _log_admin_action(admin, "Updated institution", data.get("name", str(institution_id)),
                           meta={"changes": safe_changes})
        return {"status": "success", "institution": data}
    except ValueError as e:
        return {"status": "error", "message": str(e)}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/admin/openai-usage")
def api_openai_usage(days: int = 30, admin: str = Depends(require_admin)):
    from auth.openai_usage import get_openai_usage, get_openai_costs, get_openai_credit_balance
    usage = get_openai_usage(days_back=days)
    costs = get_openai_costs(days_back=days)
    credit = get_openai_credit_balance()
    usage["total_usd"] = costs.get("total_usd") if costs.get("available") else None
    usage["credit_total"] = credit.get("total_granted") if credit.get("available") else None
    usage["credit_used"] = credit.get("total_used") if credit.get("available") else None
    usage["credit_available"] = credit.get("total_available") if credit.get("available") else None
    return usage

@app.delete("/admin/institutions/{institution_id}")
def api_delete_institution(institution_id: int, admin: str = Depends(require_admin)):
    try:
        result = delete_institution(institution_id)
        _log_admin_action(
            admin, "Deleted institution", result["institution_name"],
            meta={"licenses_removed": result["licenses_removed"]},
        )
        return {"status": "success", "deleted": result}
    except ValueError as e:
        return {"status": "error", "message": str(e)}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/locations")
def get_locations(req: dict):
    validation = validate_license(req.get("activation_code", ""))
    if not validation.get("valid"):
        raise HTTPException(status_code=401, detail="Invalid or expired activation code.")
    conn = get_hospital_connection(validation.get("db_name"), validation.get("db_server"), validation.get("db_user"), validation.get("db_password"))
    if not conn:
        return {"locations": []}
    try:
        cursor = conn.cursor()
        institution_type = validation.get("institution_type", "diagnostic")
        if institution_type == "hospital":
            cursor.execute("SELECT LocName FROM tblHOSPDTLS ORDER BY LocName")
        else:
            cursor.execute("SELECT LOCATIONNAME FROM mstlocation WHERE ACTIVE = 1 ORDER BY LOCATIONNAME")
        names = [row[0] for row in cursor.fetchall()]
        return {"locations": names}
    finally:
        conn.close()
# ---------- Admin: licenses (auth required) ----------

@app.post("/release-device")
def release_device_lock(req: dict):
    from auth.device_lock import release_device
    code = req.get("activation_code", "")
    if code:
        release_device(code.upper())
    return {"status": "success"}

@app.get("/admin/licenses")
def api_list_licenses(admin: str = Depends(require_admin)):
    return {"status": "success", "licenses": list_licenses()}

@app.get("/admin/groq-quota")
def api_groq_quota(admin: str = Depends(require_admin)):
    from auth.groq_quota import get_groq_quota
    return get_groq_quota()

@app.get("/admin/all-quotas")
def api_all_quotas(admin: str = Depends(require_admin)):
    from auth.groq_quota import get_groq_quota
    from auth.openrouter_quota import get_openrouter_quota
    return {
        "groq": get_groq_quota(),
        "openrouter": get_openrouter_quota(),
    }

@app.patch("/admin/licenses/{code}")
def update_license_endpoint(code: str, req: dict, admin=Depends(require_admin)):
    try:
        updated = update_license(code, **req)
        return {"status": "success", "license": updated}
    except ValueError as e:
        return {"status": "error", "message": str(e)}

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
            email=req.email,
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
from fastapi.responses import StreamingResponse
from pydantic import BaseModel




class ExcelExportRequest(BaseModel):
    period: str = "today"
    report_type: str = "collection"
    activation_code: str = ""
    location: str = ""

@app.delete("/admin/licenses/{code}")
def api_delete_license(code: str, admin: str = Depends(require_admin)):
    ok = delete_license(code)
    if not ok:
        return {"status": "error", "message": "Code not found"}
    _log_admin_action(admin, "Deleted license", code)
    return {"status": "success", "message": "License deleted"}
# */

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
    # get_settings() itself returns the real decrypted smtp_password —
    # notifications/email.py needs that to actually send mail. But the
    # API response to the browser should never include it, same reasoning
    # as institution db_password: a has_smtp_password flag is enough for
    # the UI to show "(saved)" without ever putting the real value where
    # a network tab or a compromised browser extension could read it.
    settings_data = get_settings()
    has_smtp_password = bool(settings_data.get("smtp_password"))
    settings_data["smtp_password"] = ""
    settings_data["has_smtp_password"] = has_smtp_password
    return {"status": "success", "settings": settings_data}


@app.get("/admin/available-modules")
def api_available_modules(admin: str = Depends(require_admin)):
    from auth.table_access import REAL_TABLE_TO_CATEGORY
    modules = sorted(set(REAL_TABLE_TO_CATEGORY.values()))
    return {"status": "success", "modules": modules}

@app.post("/verify-otp")
def verify_otp_endpoint(req: dict):
    activation_code = req.get("activation_code", "")
    otp = req.get("otp", "")

    validation = validate_license(activation_code)
    two_factor_method = validation.get("two_factor_method", "email") if validation.get("valid") else "email"

    if two_factor_method == "totp":
        from auth.totp_2fa import verify_totp_code
        if not verify_totp_code(validation.get("totp_secret"), otp):
            return {"status": "error", "answer": "Incorrect code."}
    else:
        from auth.email_otp import verify_otp
        result = verify_otp(activation_code, otp)
        if not result["valid"]:
            return {"status": "error", "answer": result["reason"]}

    validation = validate_license(activation_code)
    if not validation.get("valid"):
        return {"status": "error", "answer": "Session expired. Please enter your activation code again."}

    return {
        "status": "success",
        "mode": "premium",
        "role": validation.get("role", "viewer"),
        "hospital_name": validation.get("hospital_name"),
        "institution_type": validation.get("institution_type", "diagnostic"),
        "plan": validation.get("plan"),
    }
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
from fastapi.responses import FileResponse

#@app.get("/download/{filename}")

#def download_file(filename: str):
 #   return FileResponse(f"exports/{filename}", filename=filename)


@app.post("/admin/notifications/test")
def api_test_notifications(admin: str = Depends(require_admin)):
    email_ok, email_msg = send_alert_email(
        "Sahasra AI Agent — Notification Test",
        f"This confirms your email notification setup is working correctly.\n\n"
        f"Triggered by: {admin}\n"
        f"From: Sahasra AI Agent Admin Panel"
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

@app.get("/public-config")
def get_public_config():
    return {
        "api_url": os.environ.get("PUBLIC_API_URL", "http://127.0.0.1:8000"),
        "widget_url": os.environ.get("PUBLIC_WIDGET_URL", ""),
    }
# ---------- Admin: audit log (auth required) ----------
# Real compliance data — every premium query, invalid activation attempt,
# and now every admin action (who created/edited/revoked what), read
# straight from audit/audit.log.
@app.get("/admin/licenses/{code}/totp-qr")
def get_totp_qr(code: str, admin: str = Depends(require_admin)):
    from auth.totp_2fa import generate_totp_secret, generate_qr_code_data_uri
    from auth.license_service import update_license, validate_license

    validation = validate_license(code)
    if not validation.get("valid"):
        return {"status": "error", "message": "License not found"}

    secret = validation.get("totp_secret")
    if not secret:
        secret = generate_totp_secret()
        update_license(code, totp_secret=secret)

    qr_data_uri = generate_qr_code_data_uri(secret, validation.get("hospital_name", "Hospital"), code)
    manual_code = " ".join(secret[i:i+4] for i in range(0, len(secret), 4))

    return {"status": "success", "qr_code": qr_data_uri, "manual_code": manual_code}


@app.get("/widget-config")
def get_widget_config():
    settings = get_settings()
    return {
        "title": settings["widget_title"],
        "subtitle": settings["widget_subtitle"],
        "welcome_message": settings["widget_welcome_message"],
        "primary_color": settings["widget_primary_color"],
        "secondary_color": settings["widget_secondary_color"],
        "bg_color": settings["widget_bg_color"],
        "width_px": settings["widget_width_px"],
        "height_px": settings["widget_height_px"],
        "icon_url": settings["widget_icon_url"],
        "disclaimer_text": settings["widget_disclaimer_text"],
        "footer_text": settings["widget_footer_text"],
        "role_suggestions": settings["widget_role_suggestions"],
        "max_history": settings["widget_max_history"],
        "session_timeout_min": settings["widget_session_timeout_min"],
        "preview_toast_enabled": settings["widget_preview_toast_enabled"],
        "escalate_phone": settings["widget_escalate_phone"],
        "escalate_message": settings["widget_escalate_message"],
        "idle_nudge_enabled": settings["widget_idle_nudge_enabled"],
        "idle_nudge_minutes": settings["widget_idle_nudge_minutes"],
        "idle_nudge_message": settings["widget_idle_nudge_message"],
    }

@app.get("/admin/audit")
def api_get_audit(
    limit: int = 500,
    search: str = None,
    event_type: str = None,
    date_from: str = None,
    date_to: str = None,
    institution_id: int = None,
    admin: str = Depends(require_admin),
):
    events = read_audit_log(
        limit=limit, search=search, event_type=event_type,
        date_from=date_from, date_to=date_to, institution_id=institution_id,
    )
    return {"status": "success", "events": events}


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

from auth.usage_limiter import get_token_plan, set_token_plan, get_usage_today
class LimitRequest(BaseModel):
    period_type: str
    token_limit: int

@app.get("/admin/institutions/{hospital_id}/limit")
def get_institution_limit(hospital_id: str):
    return get_token_plan(hospital_id)
@app.post("/admin/institutions/{hospital_id}/limit")
def set_institution_limit(hospital_id: str, req: LimitRequest):
    return set_token_plan(hospital_id, req.period_type, req.token_limit)

@app.get("/admin/institutions/{hospital_id}/usage")
def get_institution_usage(hospital_id: str):
    return get_usage_today(hospital_id)

@app.post("/usage-status")
def usage_status(req: dict):
    validation = validate_license(req.get("activation_code", ""))
    if not validation.get("valid"):
        return {"error": "Invalid or expired activation code."}
    institution_code = validation.get("institution_code") or validation.get("db_name")
    from auth.usage_limiter import get_usage_today
    usage = get_usage_today(institution_code)
    pct = round((usage["used"] / usage["limit"]) * 100) if usage["limit"] else 0
    return {**usage, "pct": pct, "institution_code": institution_code}
@app.post("/generate-excel")
async def generate_excel(req: ExcelExportRequest):
    validation = validate_license(req.activation_code)
    if not validation.get("valid"):
        raise HTTPException(status_code=401, detail="Invalid or expired activation code.")

    import asyncio
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None,
        lambda: run_excel_export(
            report_type=getattr(req, "report_type", None) or "collection",
            period=req.period or "today",
            db_name=validation.get("db_name"),
            db_server=validation.get("db_server"),
            db_user=validation.get("db_user"),
            db_password=validation.get("db_password"),
            hospital_name=validation.get("hospital_name") or "Hospital",
            location_keyword=(getattr(req, "location", None) or "").strip() or None,
        ),
    )
    if "error" in result:
        guardian.record_event(validation.get("db_name"), "excel", result["error"])
        raise HTTPException(status_code=404, detail=result["error"])

    return StreamingResponse(
        result["file"],
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{result["filename"]}"'},
    )
@app.post("/generate-pdf")
async def generate_pdf(req: PDFRequest):
    if req.client:
        from auth.whitelabel import smart_report_allowed
        if not smart_report_allowed(req.client):
            raise HTTPException(status_code=403, detail="PDF reports are not available in this chatbot.")
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

from fastapi.responses import StreamingResponse

# @app.post("/generate-excel")
# def generate_excel(period: str = "today", db_name: str = None, db_server: str = None, db_user: str = None, db_password: str = None):
#     result = export_all_branches_collection(period, db_name, db_server, db_user, db_password)
#     if "error" in result:
#         return {"error": result["error"]}
#     return StreamingResponse(
#         result["file"],
#         media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
#         headers={"Content-Disposition": f'attachment; filename="{result["filename"]}"'},
#     )


@app.post("/generate-patient-report")
async def generate_patient_report(req: PatientReportRequest):
    """
    The REAL Smart Report — looks up one specific real patient and
    builds their report from freshly-queried real data, instead of
    just re-wrapping whatever the last chat answer happened to say.
    """
    if req.client:
        from auth.whitelabel import smart_report_allowed
        if not smart_report_allowed(req.client):
            raise HTTPException(status_code=403, detail="PDF reports are not available in this chatbot.")
    validation = validate_license(req.activation_code)
    if not validation.get("valid"):
        raise HTTPException(status_code=401, detail="Invalid or expired activation code.")

    role = validation.get("role", "viewer")
    db_name = validation.get("db_name")
    hospital_name = validation.get("hospital_name", "Hospital")
    db_server = validation.get("db_server")
    db_user = validation.get("db_user")
    db_password = validation.get("db_password")

    from agent.agent import _data_chain, _BYOK_USER_MESSAGES
    from agent.llm_providers import ByokUnavailable, ByokOptInRequired
    try:
        # patient data is summarised with the institution's own AI key when it has one; never silently AthenTech's
        chain = _data_chain(validation.get("institution_code") or db_name, True)
    except ByokOptInRequired:
        raise HTTPException(status_code=503, detail=_BYOK_USER_MESSAGES["opt_in_required"])
    except ByokUnavailable:
        raise HTTPException(status_code=503, detail=_BYOK_USER_MESSAGES["unavailable"])
    if not chain:
        raise HTTPException(status_code=503, detail="No LLM provider is currently configured.")
    _, agent_llm = chain[0]

    import asyncio
    loop = asyncio.get_event_loop()

    try:
        import contextvars
        _ctx = contextvars.copy_context()      # carries the "own AI key" flag into the worker thread (no shared-AI fallback)
        report_data = await loop.run_in_executor(
            None, _ctx.run, build_patient_report_data, req.patient_identifier, db_name, role, hospital_name, agent_llm,
            db_server, db_user, db_password,
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

@app.get("/health")
def health():
    """
    Lightweight readiness check for IIS / monitoring.
    Does not require auth. Does not open hospital DBs by default
    (that would make health flaky if one hospital server is down).
    """
    status = {
        "status": "ok",
        "service": "sahasra-ai-agent",
        "checks": {},
    }
    overall = "ok"

    # licenses.db readable
    try:
        from database.license_db import get_conn
        conn = get_conn()
        conn.execute("SELECT 1").fetchone()
        conn.close()
        status["checks"]["licenses_db"] = "ok"
    except Exception as e:
        status["checks"]["licenses_db"] = f"error: {e}"
        overall = "degraded"

    # encryption key configured (needed for institution passwords)
    try:
        if settings.encryption_key:
            status["checks"]["encryption_key"] = "ok"
        else:
            status["checks"]["encryption_key"] = "missing"
            overall = "degraded"
    except Exception as e:
        status["checks"]["encryption_key"] = f"error: {e}"
        overall = "degraded"

    # settings readable
    try:
        get_settings()
        status["checks"]["settings"] = "ok"
    except Exception as e:
        status["checks"]["settings"] = f"error: {e}"
        overall = "degraded"

    status["status"] = overall
    code = 200 if overall == "ok" else 503
    return JSONResponse(content=status, status_code=code)
# ---------- Public: ask ----------
@app.get("/admin/institutions-usage")
def api_institutions_usage(admin: str = Depends(require_admin)):
    from auth.usage_limiter import get_all_institutions_usage
    from database.license_db import get_conn

    conn = get_conn()
    rows = conn.execute("SELECT id, name, client_prefix FROM institutions").fetchall()
    conn.close()
    institutions = [dict(r.items()) for r in rows]

    usage = get_all_institutions_usage(institutions)
    return {"status": "success", "usage": usage}
@app.post("/ask")
def ask_question(req: QueryRequest, request: Request):   # sync -> FastAPI runs it in a worker thread; LLM/SQL waits can no longer freeze the server
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
        db_server = None
        db_user = None
        db_password = None
        institution_code = None
        institution_type = "diagnostic"

        if req.activation_code:
            client_ip = request.client.host if request.client else "unknown"
            from auth.activation_lockout import is_locked_out, record_failed_attempt, clear_failed_attempts

            lockout = is_locked_out(client_ip)
            if lockout["locked_out"]:
                return {
                    "status": "error",
                    "answer": "Too many invalid activation code attempts. Please wait 15 minutes and try again.",
                }

            validation = validate_license(req.activation_code)
            if validation.get("valid"):
                clear_failed_attempts(client_ip)
                if req.client and str(validation.get("institution_code") or "").upper() != req.client.strip().upper():
                    return {"status": "error", "answer": "This activation code is not valid for this chatbot."}

                from auth.device_lock import check_and_bind_device, release_device
                fingerprint = req.device_fingerprint or "unknown"
                device_check = check_and_bind_device(req.activation_code.upper(), fingerprint)
                if not device_check["allowed"]:
                    return {
                        "status": "error",
                        "answer": "This activation code is already logged in on another device. Please log out there first, or contact your admin.",
                    }
                if req.question.strip().lower() in ("athentech mode", "about athentech", "about-us"):
                    audit(event="athentech_mode_entry", role=role, code=req.activation_code, question=req.question)
                    return {
                        "status": "success",
                        "answer": "You're now in AthenTech Info mode. Ask me anything about AthenTech the company — type 'exit' to leave this mode.",
                        "mode": "athentech_info",
                    }
                is_validate_ping_early = req.question.strip().lower() == "validate"
                if is_validate_ping_early:
                    two_factor_method = validation.get("two_factor_method", "email")

                    if two_factor_method == "totp":
                        if not validation.get("totp_secret"):
                            from auth.totp_2fa import generate_totp_secret, generate_qr_code_data_uri
                            secret = generate_totp_secret()
                            update_license(req.activation_code, totp_secret=secret)
                            qr_data_uri = generate_qr_code_data_uri(
                                secret, validation.get("hospital_name", "your hospital"), req.activation_code
                            )
                            return {
                                "status": "success",
                                "mode": "otp_required",
                                "otp_method": "totp",
                                "totp_first_setup": True,
                                "qr_code": qr_data_uri,
                                "answer": "Scan this QR code with your authenticator app (Google Authenticator, Authy, etc.), then enter the 6-digit code it shows.",
                            }
                        return {
                            "status": "success",
                            "mode": "otp_required",
                            "otp_method": "totp",
                            "answer": "Enter the 6-digit code from your authenticator app.",
                        }

                    from auth.email_otp import generate_and_send_otp
                    otp_result = generate_and_send_otp(
                        req.activation_code, validation.get("email"), validation.get("hospital_name", "your hospital")
                    )
                    if not otp_result["sent"]:
                        return {
                            "status": "error",
                            "answer": f"Could not send verification code: {otp_result['reason']}",
                        }
                    return {
                        "status": "success",
                        "mode": "otp_required",
                        "otp_method": "email",
                        "answer": "A verification code was sent to the registered email. Enter it to continue.",
                    }
                # Per-code limit, separate from the per-IP one above —
                # protects each hospital's fair share independently of
                # how many other users happen to share their network/IP.
                code_key = req.activation_code.upper()
                now_ts = time.time()
                code_hits = [t for t in CODE_RATE.get(code_key, []) if now_ts - t < WINDOW]
                per_code_limit = get_settings()["rate_limit_per_minute"]
                if len(code_hits) >= per_code_limit:
                    return {
                        "status": "error",
                        "answer": "This activation code has made too many requests in the last minute. Please wait a moment and try again.",
                    }
                code_hits.append(now_ts)
                CODE_RATE[code_key] = code_hits

                is_premium = True
                role = validation.get("role", "viewer")
                db_name = validation.get("db_name", "hospital_demo")
                hospital_name = validation.get("hospital_name", "Hospital")
                db_server = validation.get("db_server")
                db_user = validation.get("db_user")
                db_password = validation.get("db_password")
                institution_code = validation.get("institution_code") or db_name 
                institution_type = validation.get("institution_type", "diagnostic") # fallback if inst lookup failed
            else:
                record_failed_attempt(client_ip)
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
        if is_premium and is_validate_ping:      # warm the chip check so the first real answer already has verified chips
            verified_chips(role, institution_code, institution_type, db_name, db_server, db_user, db_password, hospital_name)

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
                "institution_type": institution_type if is_premium else None,
                "plan": validation.get("plan") if is_premium else None,
            }

        try:
            from agent import confidence as _conf
            _conf.begin(req.question)
        except Exception:
            _conf = None
        answer, tokens_used = ask_agent(
            question=req.question,
            db_name=db_name,
            chat_history=history,
            is_premium=is_premium,
            role=role,
            hospital_name=hospital_name,
            db_server=db_server,
            db_user=db_user,
            db_password=db_password,
            institution_code=institution_code,
            institution_type=institution_type,
        )

        if is_premium:
            audit(
                event="premium_query",
                role=role,
                code=req.activation_code,
                question=req.question,
                answer=answer,
                tokens_used=tokens_used,
                meta={"db_name": db_name, "hospital": hospital_name})
            

        _conf_res, _answer_id, _explain_pub = None, None, None
        if is_premium and _conf is not None:
            try:
                from agent import answer_log as _alog
                _conf_res = _conf.result()
                _full = _conf.explain(include_sql=True)
                _answer_id = _alog.log_answer(institution_code, role, req.question, answer, _conf_res, _full)
                # End users see the method and tables; only admins see the SQL text.
                _explain_pub = _conf.explain(include_sql=(role == "admin"))
            except Exception:
                pass

        usage_warning = None
        if is_premium:
            budget_after = record_usage(institution_code, tokens_used)
            pct = round((budget_after["used"] / budget_after["limit"]) * 100) if budget_after["limit"] else 0
            if pct >= 50:
                usage_warning = f"You've used {pct}% of your token allowance this {budget_after['period_type']}."

        return {
            "status": "success",
            "answer": answer,
            "mode": "premium" if is_premium else "normal",
            "role": role if is_premium else None,
            "hospital_name": hospital_name if is_premium else None,
            "usage_warning": usage_warning,
            "confidence": _conf_res,
            "answer_id": _answer_id,
            "explain": _explain_pub,
            "suggestions": suggest_followups(req.question, answer, institution_type, verified=verified_chips(role, institution_code, institution_type, db_name, db_server, db_user, db_password, hospital_name)) if is_premium else [],
        }

    except Exception as e:
        import traceback
        error_text = traceback.format_exc()
        print(error_text)
        try:
            guardian.record_event(locals().get("db_name"), "ask", str(e))
        except Exception:
            pass
        with open("crash_log.txt", "a", encoding="utf-8") as f:
            from datetime import datetime
            f.write(f"\n{'='*60}\n{datetime.now().isoformat()}\n{error_text}\n")
        raise

class FeedbackRequest(BaseModel):
    activation_code: str
    answer_id: int
    vote: str
    note: str = ""
    answer_text: str = ""


@app.post("/ask/feedback")
def ask_feedback(req: FeedbackRequest):
    validation = validate_license(req.activation_code)
    if not validation.get("valid"):
        return {"status": "error", "message": "Invalid or expired activation code."}
    if req.vote not in ("up", "down"):
        return {"status": "error", "message": "Invalid vote."}
    inst = validation.get("institution_code") or validation.get("db_name") or "hospital_demo"
    from agent import answer_log
    saved = answer_log.set_vote(req.answer_id, inst, req.vote, (req.note or "")[:300])
    if saved and req.vote == "down" and req.answer_text:
        answer_log.attach_preview(req.answer_id, inst, req.answer_text[:600])
    return {"status": "success" if saved else "error"}


@app.get("/admin/answer-review")
def api_answer_review(view: str = "open", client: str = "", limit: int = 50, offset: int = 0,
                      admin: str = Depends(require_admin)):
    from agent import answer_log
    return {"status": "success", "rows": answer_log.list_rows(view, client or None, limit, offset),
            "stats": answer_log.stats()}


class ResolveRequest(BaseModel):
    note: str = ""


@app.post("/admin/answer-review/{answer_id}/resolve")
def api_answer_review_resolve(answer_id: int, req: ResolveRequest, admin: str = Depends(require_admin)):
    from agent import answer_log
    return {"status": "success" if answer_log.resolve(answer_id, req.note) else "error"}


@app.get("/admin/answer-review/console", include_in_schema=False)
def answer_review_console():
    from fastapi.responses import FileResponse
    return FileResponse(os.path.join(os.path.dirname(__file__), "answer_review.html"),
                        media_type="text/html", headers={"Cache-Control": "no-store"})


@app.on_event("startup")
async def warm_athentech_cache():
    import asyncio
    from auth.athentech_info import refresh_athentech_cache

    def _warm():
        try:
            refresh_athentech_cache(force=True)
            print("[startup] AthenTech info cache warmed successfully.")
        except Exception as e:
            print(f"[startup] AthenTech cache warm failed (non-fatal): {e}")

    asyncio.get_event_loop().run_in_executor(None, _warm)

@app.post("/athentech-info")
def athentech_info_endpoint(req: dict):
    from auth.athentech_info import answer_athentech_question
    from agent.agent import _get_provider_chain

    question = req.get("question", "")
    chain = _get_provider_chain()
    if not chain:
        return {"status": "error", "answer": "No AI provider available right now."}

    _, llm = chain[0]
    answer = answer_athentech_question(question, llm)
    return {"status": "success", "answer": answer}

from auth.whitelabel import build_router as build_whitelabel_router
app.include_router(build_whitelabel_router(require_admin, _log_admin_action))

# Corporate B2B OTP portal: organisation-scoped, read-only access.
from auth.b2b_portal import build_router as build_b2b_router, initialize_b2b
app.include_router(build_b2b_router(require_admin))

@app.on_event("startup")
def initialize_b2b_contacts():
    try:
        initialize_b2b()
        print("[b2b] Admin-only corporate contact/session tables ready")
    except Exception as exc:
        print("[b2b] ERROR: B2B access unavailable; admin DB migration failed: " + str(type(exc).__name__))

app.include_router(build_chip_router(require_admin))
# Guardian-specific API aliases: keep all console requests inside the IIS rewrite
# prefix /admin/guardian/*, without changing the existing admin dashboard URLs.
@app.post('/admin/guardian/api/login')
def guardian_api_login(req: AdminLoginRequest):
    return api_admin_login(req)

@app.get('/admin/guardian/api/status')
def guardian_api_status(admin: str = Depends(require_admin)):
    return api_guardian_status(admin)

@app.get('/admin/guardian/api/selfcheck/{code}')
def guardian_api_selfcheck(code: str, admin: str = Depends(require_admin)):
    return api_guardian_selfcheck(code, admin)

@app.get('/admin/guardian/api/diagnostics/{code}')
def guardian_api_diagnostics(code: str, refresh: bool = False, admin: str = Depends(require_admin)):
    return api_client_diagnostics(code, refresh, admin)

@app.get('/admin/guardian/api/schema-check/{code}')
def guardian_api_schema_check(code: str, admin: str = Depends(require_admin)):
    return guardian_schema_check(code, admin)

@app.get('/admin/guardian/api/support-report')
def guardian_api_support_report(admin: str = Depends(require_admin)):
    return guardian_support_report(admin)


@app.get("/admin/ops/summary")
def sahasra_ops_summary(admin: str = Depends(require_admin)):
    """Per-worker aggregate counters; authenticated administrators only."""
    return ops_summary()
