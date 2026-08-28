from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from agent.agent import ask_agent
from langchain_core.messages import HumanMessage, AIMessage

app = FastAPI(title="Sahasra AI Agent")

# Allow testing from browser
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
    activation_code: str
    question: str
    chat_history: Optional[List[Message]] = []

# Simple mock activation codes
VALID_CODES = {
    "ATH-1001": "hospital_demo",
    "ATH-1002": "hospital_demo"
}

@app.get("/")
def home():
    return {"message": "Sahasra AI Agent is running"}

@app.post("/ask")
async def ask_question(req: QueryRequest):
    # 1. Validate activation code
    if req.activation_code not in VALID_CODES:
        raise HTTPException(status_code=401, detail="Invalid activation code")

    db_name = VALID_CODES[req.activation_code]

    # 2. Convert chat history
    history = []
    for msg in req.chat_history:
        if msg.role == "user":
            history.append(HumanMessage(content=msg.content))
        else:
            history.append(AIMessage(content=msg.content))

    # 3. Call the agent
    try:
        answer = ask_agent(req.question, db_name, history)
        return {
            "status": "success",
            "answer": answer
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))