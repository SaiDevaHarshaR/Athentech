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

| Mode               | Trigger               | Data                                    |
|------              |---------              |------                                   |
| Public / AthenTech | No code               | Product info, intents, demo capture     |
| Premium            | Valid activation code | That hospital’s MSSQL only, role-scoped |

Roles (Doctor, Nurse, Lab Tech, Reception, Viewer, …) map to table categories. Reception does not get lab result tables. Admin panel can change the matrix without a redeploy.

---

## Stack that survived production

- **API:** FastAPI + Uvicorn (Windows service via NSSM, IIS reverse proxy)
- **Agent:** LangChain tool loop- `describe_table`, `run_sql_query`, department/TAT/collection tools
- **LLMs:** Groq default, multi-provider chain + per-institution BYOK, exhaustion-aware fallback
- **DB:** Per-hospital MSSQL (pyodbc), licenses/settings in SQLite
- **Guards:** SELECT-only, banned keywords, schema validation, output redaction, wall-clock + tool-round budgets
- **Ops:** Answer audit, confidence hooks, Langfuse tracing, health endpoint
- **Frontend:** Embeddable widget (vanilla), admin panel for institutions / licenses / roles

---

## Architecture (honest version)

Widget / Admin UI

|

v

FastAPI (main.py)

|

+-- /ask                     agent tool loop

+-- /athentech-info          public product answers

+-- /athentech-demo-request  lead form -> SMTP

+-- /admin/*                 licenses, roles, audit

+-- /health

|

+-- licenses.db              institutions, encrypted creds, settings

+-- Hospital MSSQL           per-institution server/db/user


Premium path: validate code -> decrypt connection -> bind role -> tool loop -> grounded answer.  
History is truncated. Tool rounds are capped. Budget is real wall-clock, not hope.

---

## The hard parts (why this isn’t a weekend demo)

- **Schema hallucination** - models invent column names. Fixed with mandatory describe + pre-exec validation + closest-column hints.
- **Date filters** - equality on datetime columns is poison on MSSQL. Forced range patterns + `SET DATEFORMAT ymd`.
- **Multi-tenancy** - credentials and results must never cross hospitals. Connection params come only from the validated license row.
- **Latency** - free-form multi-table questions were 30-60s+. Curated intents + answer cache for the hot path.
- **Provider limits** - shared keys exhaust. BYOK path never touches AthenTech quota; ContextVars keep the chains separate.
- **Windows deploy** - single NSSM service, ARR, static widget under `/widget`. Partial deploys will pause the service; treat that as a first-class failure mode.

---

## Run it locally

```bash
git clone https://github.com/SaiDevaHarshaR/Athentech.git
cd Athentech
python -m venv venv
# Windows: venv\Scripts\activate
source venv/bin/activate
pip install -r requirements.txt
```
.env needs at least:

```Text
GROQ_API_KEY=...
# optional: TAVILY_API_KEY, OPENAI_API_KEY, etc.
# MSSQL_* for a default hospital connection
```

```Bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```
Open the widget under widget_files/ or hit /health.

Production notes live in deployment/ and DEPLOYMENT.md.
ODBC Driver 17 or 18 for SQL Server is required for premium mode.

## Repo map

agent/          tool loop, guards, intents, confidence, heal
auth/           licenses, roles, table access, BYOK, AthenTech intents
database/       hospital connections + license store
reports/        PDF / Excel generators
observability/  tracing, metrics, alerts
widget_files/   embeddable chat UI
admin/          static admin panel
tests/          a lot of “this used to lie about revenue” coverage


## Status

Production for AthenTech hospital clients.

Public widget for athentech.co.in product questions + demo booking.

Not a research prototype. The scars are in the commit history.
If you’re evaluating this as a portfolio piece: look at agent/tools.py, agent/guard_hooks.py, the role matrix, and how provider isolation is enforced under concurrent load. That’s the work.