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
    set_license_status,
    get_role_permissions,
    update_role_permissions,
)
from auth.admin_auth import require_admin, create_admin_token, check_admin_credentials
from audit.log import audit
from reports.pdf_generator import generate_smart_report
from database.license_db import init_license_db, seed_demo_institutions
from config import settings

app = FastAPI(title="Sahasra AI Agent")

RATE = {}
LIMIT = 300
WINDOW = 60

init_license_db()
seed_demo_institutions()

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
    # Rate limit
    ip = request.client.host if request.client else "unknown"
    now = time.time()
    hits = [t for t in RATE.get(ip, []) if now - t < WINDOW]
    if len(hits) >= LIMIT:
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
    valid_days: int = 90


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


class AdminLoginRequest(BaseModel):
    username: str
    password: str


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
        # ADMIN_PASSWORD_HASH / ADMIN_SECRET_KEY not configured yet.
        raise HTTPException(status_code=500, detail=str(e))

    if not ok:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_admin_token(req.username)
    return {"status": "success", "token": token}


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
        return {"status": "success", "institution": data}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ---------- Admin: licenses (auth required) ----------

@app.get("/admin/licenses")
def api_list_licenses(admin: str = Depends(require_admin)):
    return {"status": "success", "licenses": list_licenses()}


@app.post("/admin/licenses/generate")
def api_generate_license(req: GenerateLicenseRequest, admin: str = Depends(require_admin)):
    try:
        data = create_license(
            institution_id=req.institution_id,
            role=req.role,
            phone=req.phone,
            dob_year=req.dob_year,
            plan=req.plan,
            valid_days=req.valid_days,
        )
        return {"status": "success", "license": data}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.post("/admin/licenses/status")
def api_set_license_status(req: LicenseStatusRequest, admin: str = Depends(require_admin)):
    ok = set_license_status(req.code, req.status)
    if not ok:
        return {"status": "error", "message": "License not found"}
    return {"status": "success", "message": f"License marked {req.status}"}


@app.post("/admin/licenses/revoke")
def api_revoke_license(req: RevokeLicenseRequest, admin: str = Depends(require_admin)):
    ok = revoke_license(req.code)
    if not ok:
        return {"status": "error", "message": "Code not found"}
    return {"status": "success", "message": "License revoked"}


# ---------- Admin: roles (auth required) ----------

@app.get("/admin/roles")
def api_get_roles(admin: str = Depends(require_admin)):
    return {"status": "success", "roles": get_role_permissions()}


@app.put("/admin/roles")
def api_update_role(req: RolePermissionUpdate, admin: str = Depends(require_admin)):
    update_role_permissions(req.role, req.tables)
    return {"status": "success"}


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

    pdf_file = generate_smart_report(data)

    return StreamingResponse(
        pdf_file,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=sahasra_report.pdf"},
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
                return {
                    "status": "error",
                    "answer": "Invalid or expired activation code.",
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
