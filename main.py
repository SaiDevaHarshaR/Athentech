from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from agent.agent import ask_agent
from langchain_core.messages import HumanMessage, AIMessage

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
        for msg in req.chat_history:
            if msg.role == "user":
                history.append(HumanMessage(content=msg.content))
            else:
                history.append(AIMessage(content=msg.content))

        is_premium = bool(req.activation_code)

        answer = ask_agent(
            question=req.question,
            db_name="hospital_demo",
            chat_history=history,
            is_premium=is_premium
        )

        return {
            "status": "success",
            "answer": answer
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))