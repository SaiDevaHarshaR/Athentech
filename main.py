from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from agent.agent import ask_agent
from langchain_core.messages import HumanMessage, AIMessage
from auth.validate_code import validate_activation_code_mock
from auth.roles import Role

app = FastAPI(title="Sahasra AI Agent")

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
            "role": role if is_premium else None
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))