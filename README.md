# Sahasra AI Agent

Hospital staff kept asking the same questions into empty air:

> "How much did we collect yesterday at LOC04?"  
> "TAT compliance for radiology this week?"  
> "Cash vs UPI split for the last 30 days?"

Sahasra already had the data. Nobody had a sane way to *ask* it.

This is the agent that sits on top of live hospital MSSQL, plans tool calls, stays inside role boundaries, and answers from real rows - not vibes(Hallucination).

Built for [AthenTech](https://www.athentech.co.in/) / Sahasra HIS. Running in production.

---

## What it actually does

Enter an activation code -> the agent is locked to **one** hospital’s database.

It does not “know” medicine. It:
1. Discovers real columns (`describe_table`)
2. Writes SELECT-only SQL under role ACLs
3. Validates columns against `INFORMATION_SCHEMA` before execution
4. Falls back to curated fixed queries for the questions that always break free-form generation
5. Returns grounded numbers or says it doesn’t know

Public / AthenTech-only mode answers product questions and can open a demo-booking form. Premium mode never invents clinical or billing figures.

---

## Modes

| Mode | Trigger | Data |
|------|---------|------|
| Public / AthenTech | No code | Product info, intents, demo capture |
| Premium | Valid activation code | That hospital’s MSSQL only, role-scoped |

Roles (Doctor, Nurse, Lab Tech, Reception, Viewer, …) map to table categories. Reception does not get lab result tables. Admin panel can change the matrix without a redeploy.

---

## Stack that survived production

- **API:** FastAPI + Uvicorn (Windows service via NSSM, IIS reverse proxy)
- **Agent:** LangChain tool loop — `describe_table`, `run_sql_query`, department/TAT/collection tools
- **LLMs:** Groq default, multi-provider chain + per-institution BYOK, exhaustion-aware fallback
- **DB:** Per-hospital MSSQL (pyodbc), licenses/settings in SQLite
- **Guards:** SELECT-only, banned keywords, schema validation, output redaction, wall-clock + tool-round budgets
- **Ops:** Answer audit, confidence hooks, Langfuse tracing, health endpoint
- **Frontend:** Embeddable widget (vanilla), admin panel for institutions / licenses / roles

---

## Architecture (honest version)
