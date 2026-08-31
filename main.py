from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from agent.agent import ask_agent
from langchain_core.messages import HumanMessage, AIMessage
from auth.validate_code import validate_activation_code_mock
from auth.roles import Role
from fastapi import Request
from fastapi.responses import JSONResponse
import time
from audit.log import audit
from fastapi.responses import StreamingResponse
from reports.pdf_generator import generate_smart_report

app = FastAPI(title="Sahasra AI Agent")


RATE = {}
LIMIT = 30        
WINDOW = 60
# Allow frontend to call the API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class Message(BaseModel):
    role: str
    content: str

class QueryRequest(BaseModel):
    question: str
    activation_code: Optional[str] = None
    chat_history: Optional[List[Message]] = []

@app.get("/")
def home():
    return {"message": "Sahasra AI Agent is running"}

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
class PDFRequest(BaseModel):
    title: str = "Sahasra AI Report"
    hospital_name: str = "Hospital"
    role: str = "Staff"
    activation_code: str = ""
    content_lines: list[str] = []   # bullet points / answer lines

@app.post("/generate-pdf")
async def generate_pdf(req: PDFRequest):
    # Convert answer lines into the structure your template expects
    tests = []
    for i, line in enumerate(req.content_lines):
        tests.append({
            "name": line[:80],
            "value": "",
            "unit": "",
            "range": "",
            "status": "normal",
            "percentage": 70,
            "comment": line
        })

    data = {
        "report_title": req.title,
        "hospital_name": req.hospital_name,
        "user_role": req.role,
        "activation_code": req.activation_code,
        "content_lines": req.content_lines
    }

    pdf_file = generate_smart_report(data)

    return StreamingResponse(
        pdf_file,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=sahasra_report.pdf"}
    )
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
            validation = validate_activation_code_mock(req.activation_code)
            if validation and validation.get("valid"):
                is_premium = True
                role = validation.get("role", "viewer")
                db_name = validation.get("db_name", "hospital_demo")
                hospital_name = validation.get("hospital_name", "Demo Hospital")
            else:
                return {
                    "status": "error",
                    "answer": "Invalid or expired activation code."
                }
        if is_premium and req.question.strip().lower() != "validate":
            audit(
                event="premium_query",
                role=role,
                code=req.activation_code,
                question=req.question,
                meta={"db_name": db_name, "hospital": hospital_name}
            )

        answer = ask_agent(
            question=req.question,
            db_name=db_name,
            chat_history=history,
            is_premium=is_premium,
            role=role,
            hospital_name=hospital_name
        )

        return {
            "status": "success",
            "answer": answer,
            "mode": "premium" if is_premium else "normal",
            "role": role if is_premium else None,
            "hospital_name": hospital_name if is_premium else None
        }

        if req.question.strip().lower() == "validate":
            return {
                "status": "success",
                "answer": "Code validated",
                "mode": "premium" if is_premium else "normal",
                "role": role if is_premium else None,
                "hospital_name": hospital_name if is_premium else None
            }

        answer = ask_agent(
            question=req.question,
            db_name=db_name,
            chat_history=history,
            is_premium=is_premium,
            role=role,
            hospital_name=hospital_name
        )

        return {
            "status": "success",
            "answer": answer,
            "mode": "premium" if is_premium else "normal",
            "role": role if is_premium else None,
            "hospital_name": hospital_name if is_premium else None
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))