# Sahasra AI Agent – Athentech

**AI-powered assistant for hospitals**, built for [Athen Tech](https://athentech.in/) / Sahasra Hospital Information System.

This project provides a conversational AI that can answer questions about hospitals and doctors (public mode) or securely query a specific hospital’s live data (premium mode) using an activation code.

---

## Overview

Sahasra AI Agent is designed to become the intelligent chatbot layer on top of the Sahasra HIS platform. It will eventually replace external tools like Zoho Chat by offering a native, hospital-specific AI assistant.

### Core Flow (Premium Mode)

1. Hospital receives an **Activation Code**
2. User enters the code → system connects **only** to that hospital’s database
3. All answers are generated **strictly from the hospital’s data** (no general knowledge)
4. Supports full **chat history** (follow-up questions work naturally)
5. Answers can be returned as clean text (and later as **Smart Reports** in PDF / Excel)
6. Frontend is a lightweight chat widget ready for website embedding

---

## Two Operating Modes

| Mode       | Trigger                          | Data Source                          | Use Case                                      |
|------------|----------------------------------|--------------------------------------|-----------------------------------------------|
| **Normal** | No activation code               | Tavily Web Search                    | Public questions about hospitals, doctors, specialties in India |
| **Premium**| Valid Activation Code            | Hospital’s own database only         | Staff / authorized users asking about patients, admissions, labs, occupancy, etc. |

### Premium Mode Examples
- “Show me all patients”
- “Who is the oldest patient?”
- “List current admissions”
- “How many patients are in Cardiology?”
- “Show admissions for today”

The agent is strictly instructed to answer **only** from the connected hospital database and never invent information.

---

## Features

- **Activation Code system** – Isolates each hospital’s data
- **Database isolation** – Currently SQLite (demo), designed for real MySQL later
- **Safe SQL tool** – Only `SELECT` queries are allowed
- **Chat history** – Full multi-turn conversations
- **Clean formatting** – Bullet points + emojis (no markdown tables)
- **PDF & Excel report generators** – Ready for “Smart Report” output
- **Ready-to-embed chat widget** (`sahasra_chat_widget.html`)
- **FastAPI backend** with CORS enabled

---

## Tech Stack

| Layer          | Technology                          |
|----------------|-------------------------------------|
| Backend        | FastAPI + Uvicorn                   |
| AI Framework   | LangChain + LangGraph               |
| LLM            | Groq (`openai/gpt-oss-20b`)         |
| Web Search     | Tavily                              |
| Database       | SQLite (demo) → MySQL (planned)     |
| Reports        | ReportLab / xhtml2pdf + openpyxl    |
| Frontend       | Vanilla HTML/CSS/JS chat widget     |

---

## Project Structure
Athentech/
├── agent/
│   ├── agent.py          # Core ask_agent logic (Normal + Premium)
│   ├── prompts.py        # System prompts + schema
│   ├── tools.py          # SQL tool (safe SELECT only)
│   └── search_tool.py    # Tavily web search tool
├── auth/
│   └── validate_code.py  # Activation code validation
├── database/
│   └── connection.py     # DB connection helper
├── models/
│   └── schemas.py
├── reports/
│   ├── pdf_generator.py
│   ├── excel_generator.py
│   └── templates/
├── config.py
├── create_db.py          # Creates demo SQLite database
├── main.py               # FastAPI application
├── requirements.txt
├── hospital_demo.db
├── sahasra_chat_widget.html
└── test_*.py


---

## Setup & Installation

### 1. Clone the repository
```bash
git clone https://github.com/SaiDevaHarshaR/Athentech.git
cd Athentech
```
### 2. Create virtual environment
```bash
python  -m venv venv
source venv/bin/activate         
# or
venv\Scripts\activate      #Windows
```

### 3. Install dependencies
```bash 
pip install -r requirements.txt
```

### 4. Environment variables
```bash
Create a .env file in the root:
envGROQ_API_KEY=your_groq_api_key
TAVILY_API_KEY=your_tavily_api_key
```

### 5. Create the demo database
```Bash 
python create_db.py
```

This creates hospital_demo.db with sample patients and admissions.

Running the Project
Start the API server
```Bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```
The API will be available at: http://127.0.0.1:8000
Open the Chat Widget
Simply open sahasra_chat_widget.html in your browser.
The widget points to http://127.0.0.1:8000/ask by default.

API Usage
Endpoint: POST /ask
Request body:
JSON{
  "question": "Show me all patients",
  "activation_code": "ATH-1001",          // optional – enables Premium mode
  "chat_history": [
    {"role": "user", "content": "previous question"},
    {"role": "assistant", "content": "previous answer"}
  ]
}
Response:
JSON{
  "status": "success",
  "answer": "Here are the patients currently in the system:\n\n👤 **Ramesh Kumar**\n• UHID: UHID001\n• Age: 42 years\n..."
}



### Notes

Premium mode is intentionally restricted: the agent cannot use general knowledge or web search once an activation code is active.
All SQL queries are forced to be SELECT only for safety.
The chat widget already supports the activation-code flow and conversation history.


```
Built for Athen Tech – Sahasra Healthcare Platform

Hyderabad · Bangalore · Vijayawada · Vizag
```