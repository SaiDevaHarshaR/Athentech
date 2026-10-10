# Sahasra AI Agent

<p align="center">
  <strong>A hospital-aware AI assistant for AthenTech Sahasra HIS / LIS</strong><br>
  Live, institution-scoped data access · Role-aware tools · Admin console · Embeddable chat · Reports
</p>

---

## What it is

Sahasra AI Agent is a FastAPI service and browser-based chat experience for AthenTech. It supports public healthcare questions, institution-specific conversations backed by a hospital's Microsoft SQL Server database, and AthenTech information mode. A separate admin interface manages institutions, activation licenses, access roles, settings, usage, notifications, audit history, and white-label embeds.

> **Important:** This is an operational application, not a clinical decision system. Validate database mappings, role permissions, and generated answers against each institution's schema and policies before production use.

## Capabilities

- **Public / Normal mode** — general questions can use the configured web-search and LLM providers when Normal mode is enabled.
- **Premium mode** — an activation code resolves to an institution, role, license status, and database connection settings. The agent uses that institution's database context.
- **Role-aware data tools** — table access is constrained by configured role permissions; review and customize the defaults with the hospital's actual access policy.
- **LIS / HIS workflows** — intent-based lookups and dashboards for supported patient, billing, collection, sample, test, branch, and turnaround-time questions. Actual coverage depends on the client's schema.
- **Follow-up chat** — prior messages are passed as conversation history; suggested follow-up chips are supported.
- **Reports and exports** — Excel exports, patient Smart Reports in PDF, and report/dashboard helpers.
- **Admin console** — institutions, licenses, admin users, role permissions, settings, provider usage/quota information, audit records, and notification settings.
- **License security controls** — activation-attempt lockout, device binding, optional email/TOTP verification flow, expiry/status handling, and usage/rate limits.
- **White-label embeds** — institution branding, B2C/B2B/Admin modes, site knowledge, language options, and optional Smart Report access.
- **Operations** — health endpoint, configurable CORS, Windows Service deployment through NSSM, IIS reverse proxy, and rotating service logs.

## Architecture

```text
Browser
  ├── widget_files/       Chat widget
  └── admin/              Admin console
          │
          ▼
      IIS / HTTPS
          │ reverse proxy
          ▼
    FastAPI (main.py)
      ├── /ask and chat workflows
      ├── /admin/* management APIs
      ├── report / export APIs
      ├── white-label router
      └── /health
          │
          ├── Admin / license database (SQL Server via pyodbc)
          └── Institution-specific HIS / LIS databases (SQL Server via pyodbc)
```

The admin/license database and the hospital database connections are separate configuration concerns. The application can use shared MSSQL connection defaults from `.env`; institution records can override the hospital server, username, password, and database. Institution passwords and other supported secrets are encrypted using the configured encryption key.

## Technology

- Python, FastAPI, Uvicorn, Pydantic Settings
- LangChain / LangGraph and configurable LLM integrations (Groq, OpenAI, Anthropic, Gemini, Mistral, Cohere packages are present; the active provider depends on configuration and code path)
- Microsoft SQL Server through `pyodbc` and an installed Microsoft ODBC driver
- Tavily integration for web search
- Vanilla HTML, CSS, and JavaScript for the widget and admin UI
- ReportLab, Jinja2, Playwright, and openpyxl for report/export workflows

## Repository map

| Path | Purpose |
|---|---|
| `main.py` | FastAPI app, middleware, API routes, startup initialization |
| `config.py` | Environment-backed settings |
| `agent/` | Agent orchestration, prompts, tools, intents, schema search, guardrails, follow-ups |
| `auth/` | License validation, admin authentication, roles, encrypted secrets, rate/usage controls, white-label logic |
| `database/connection.py` | Per-institution hospital MSSQL connections |
| `database/license_db.py` | Admin/license database connection and schema initialization |
| `models/schemas.py` | Request and response models |
| `reports/` | Excel exports, patient Smart Reports, collection/TAT dashboards and reconciliation helpers |
| `notifications/` | Expiry checks, email, and webhook notifications |
| `audit/` | Audit event logging and audit history |
| `admin/` | Admin panel static assets |
| `widget_files/` | Chat widget static assets, also mounted by the API at `/widget` |
| `deployment/` | Production environment template, IIS configs, and Windows Service installer |
| `tests/` | Automated tests |
| `RUNBOOK.md` | Operational procedures for common admin tasks |
| `ROLE_PERMISSIONS_PROPOSAL.md` | Background on proposed role/table permissions |

## Requirements

- Windows is the documented production target; development can run anywhere supported by Python and the required ODBC driver.
- Python version compatible with the installed dependencies (Python 3.10+ is a reasonable baseline; verify the chosen runtime before deployment).
- Microsoft ODBC Driver 17 or 18 for SQL Server. The admin database connector specifically requests **ODBC Driver 18**.
- Network access from the API host to the admin database and each configured institution database.
- Credentials and API keys for the selected LLM provider. Tavily is needed for web-search flows.
- For production IIS deployment: IIS, URL Rewrite, Application Request Routing (ARR), NSSM, and an HTTPS binding/certificate managed by the server administrator.

## Quick start (Windows PowerShell)

Run commands from the repository root (the directory containing `main.py`).

### 1. Create and activate a virtual environment

```powershell
py -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 2. Configure `.env`

Copy `deployment/.env.production.template` to `.env` in the project root, then fill in the required values. Do not commit `.env` or real credentials.

Generate an admin password hash / bootstrap values using the project's helper:

```powershell
python auth/generate_admin_hash.py
```

Generate an encryption key using:

```powershell
python auth/generate_encryption_key.py
```

Keep the encryption key stable and backed up securely. Changing it without re-encrypting stored secrets can make those secrets unreadable.

### 3. Set the environment variables

The production template covers the LLM, shared hospital connection, admin authentication, and CORS settings. The following admin database variables are also read by `database/license_db.py` and must be configured for the SQL Server-backed license/admin database:

```dotenv
ADMIN_DB_SERVER=your-admin-sql-host
ADMIN_DB_PORT=1433
ADMIN_DB_NAME=your-admin-database
ADMIN_DB_USER=your-admin-db-user
ADMIN_DB_PASSWORD=your-admin-db-password
```

Core settings:

| Variable | Purpose |
|---|---|
| `GROQ_API_KEY` | Required by the current settings model; used when Groq is selected |
| `LLM_PROVIDER` | Provider selection; defaults to `groq` |
| `LLM_MODEL` | Optional model override, depending on provider/configuration |
| `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY` | Optional provider credentials |
| `TAVILY_API_KEY` | Web-search integration |
| `MSSQL_SERVER`, `MSSQL_DATABASE`, `MSSQL_USER`, `MSSQL_PASSWORD` | Shared/fallback hospital database connection values |
| `ADMIN_DB_SERVER`, `ADMIN_DB_PORT`, `ADMIN_DB_NAME`, `ADMIN_DB_USER`, `ADMIN_DB_PASSWORD` | Admin/license SQL Server connection |
| `ADMIN_USERNAME`, `ADMIN_PASSWORD_HASH`, `ADMIN_SECRET_KEY` | Admin login/bootstrap and signed session token settings |
| `ENCRYPTION_KEY` | Encrypts institution DB passwords and supported stored secrets |
| `ALLOWED_ORIGINS` | Comma-separated browser origins, including scheme and hostname, without trailing slashes |
| `PUBLIC_API_URL`, `PUBLIC_WIDGET_URL` | Optional public URLs used by configuration/embed helpers |

Use a least-privilege SQL login. Do not use `sa` or another write-capable account for live hospital databases. Configure each institution with its real database name and any required per-institution connection overrides in the admin console.

### 4. Start the API

```powershell
python -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

Useful local URLs:

- API root: `http://127.0.0.1:8000/`
- Health: `http://127.0.0.1:8000/health`
- Widget: `http://127.0.0.1:8000/widget/`
- OpenAPI docs (if enabled by the runtime): `http://127.0.0.1:8000/docs`

The widget also exists as static files under `widget_files/`; `widget_files/index.html` currently contains the configured API URL, so check it when moving between environments.

## First-time setup checklist

1. Confirm the admin/license SQL Server database is reachable and the service account can create/alter the required application tables.
2. Sign in to the admin console and confirm admin authentication is configured securely.
3. Add an institution with its exact database name and the correct SQL Server connection details.
4. Create an activation license for the institution and the appropriate role.
5. Confirm the selected role's table permissions match the institution's approved access policy.
6. Test the activation code and verify the database connection using known, non-sensitive test questions.
7. Test a normal-mode question, report/export workflow, and white-label configuration if those features are enabled.
8. Verify CORS, HTTPS, backups, logs, and recovery procedures before handing over access.

See [`RUNBOOK.md`](RUNBOOK.md) for institution onboarding, license generation/revocation, password rotation, and backup guidance.

## API route overview

The route definitions in `main.py` include the following groups. Exact request/response fields are defined by the Pydantic models and endpoint implementations.

| Route(s) | Purpose |
|---|---|
| `GET /` | Basic service response |
| `GET /health` | Health/readiness response |
| `POST /ask` | Chat, activation-code validation, and agent response |
| `GET /public-config`, `GET /widget-config` | Public widget configuration |
| `POST /generate-excel` | Excel export workflow |
| `POST /generate-pdf` | Smart Report PDF workflow |
| `POST /generate-patient-report` | Patient-focused Smart Report workflow |
| `/admin/login` | Admin authentication entry point |
| `/admin/users*` | Admin user management |
| `/admin/institutions*` | Institution registry and institution usage/limits |
| `/admin/licenses*` | License generation, update, status, revoke, delete, and related operations |
| `/admin/roles*` | Role permission management |
| `/admin/settings` | Application settings |
| `/admin/audit` | Audit history |
| `/admin/notifications/*` | Notification testing and expiry checks |
| `/admin/whitelabel/*` | White-label configuration and embed-related management |
| `/athentech-info` | AthenTech information endpoint |
| `/widget/*` | Static widget files mounted by FastAPI |

For the complete and current contract, inspect `main.py`, the router in `auth/whitelabel.py`, and the request models in `models/schemas.py`.

## Production deployment (Windows Server + IIS)

The files under `deployment/` document the intended split:

- IIS serves the static admin/widget assets and terminates HTTPS.
- IIS reverse-proxies API requests to Uvicorn bound to localhost.
- NSSM runs Uvicorn as the `SahasraAIAgent` Windows Service.

High-level sequence:

1. Install Python, the required ODBC driver, IIS URL Rewrite, ARR, and NSSM.
2. Copy the project to the production path and install dependencies in its virtual environment.
3. Create and populate the project-root `.env`.
4. Fill in the placeholders in `deployment/install_service.ps1` and both IIS `web.config` files.
5. Confirm ARR proxy is enabled and `ALLOWED_ORIGINS` contains the exact production origins.
6. Start the service, then test `/`, `/health`, `/admin/login`, the widget, and a real test institution.
7. Monitor `logs/service_stdout.log` and `logs/service_stderr.log`.

Follow [`deployment/README.md`](deployment/README.md) for the detailed IIS setup sequence. Do not expose the Uvicorn port publicly when IIS is intended to be the public entry point.

## Security and operational notes

- **Least privilege:** use read-only hospital SQL accounts where possible; do not connect to live client databases using `sa`.
- **Role permissions:** defaults in code are a starting proposal, not a substitute for the hospital's formally approved policy. Review `ROLE_PERMISSIONS_PROPOSAL.md` and configure permissions deliberately.
- **Activation codes:** treat them like credentials. Deliver them securely, revoke them when access should end, and avoid putting them in logs or public channels.
- **Secrets:** keep `.env` out of version control; restrict file and database access; back up the encryption key securely.
- **CORS:** set `ALLOWED_ORIGINS` to exact trusted origins. Do not use `*` with credentialed requests.
- **Audit/logs:** review audit records and service logs while protecting patient identifiers and other sensitive data.
- **SQL safety:** the agent has guarded SQL tools and read-oriented paths, but review stored procedures, reconciliation helpers, and every client-specific query before production. Do not assume every workflow is strictly read-only without verifying its implementation.
- **Clinical use:** AI output can be wrong. Do not use it as a replacement for clinical judgment, and validate all client schema mappings and report logic.
- **Backups:** schedule and test backups of the admin/license database, and keep a tested recovery procedure.

## Troubleshooting

| Symptom | Check |
|---|---|
| API does not start | `.env` values, installed packages, Python path, working directory, and service logs |
| Admin/license database connection fails | `ADMIN_DB_*` values, ODBC Driver 18 installation, network/firewall, SQL permissions, and database name |
| Hospital query fails | Institution database/server/user/password, SQL permissions, installed ODBC driver, schema differences, and service logs |
| Browser reports CORS errors | Exact frontend origin in `ALLOWED_ORIGINS`; restart the API after changing `.env` |
| Activation code is rejected | License status/expiry, institution association, lockout state, code spelling, and whether the widget's client/institution prefix matches |
| Widget calls the wrong API | `API_URL` in `widget_files/index.html` and production IIS configuration |
| White-label endpoint returns 500 | Inspect `logs/service_stderr.log` and confirm the deployed `auth/whitelabel.py` matches the intended code; use SQL Server-compatible metadata queries with named `DictRow` keys where applicable |
| Service starts but requests fail | Confirm the NSSM AppDirectory points to the project root and the service uses the intended virtual environment and `.env` |

## Tests

The repository contains `tests/` plus some standalone test scripts in the project root. Run the suite from the project root after installing dependencies:

```powershell
python -m pytest
```

Some tests or integration paths may require configured credentials, database access, or external provider access. A passing unit-test run does not replace testing against a staging SQL Server and each institution's actual schema.

## License and ownership

This README does not define a software license. Confirm the repository's licensing and distribution terms with the project owner before redistributing the code.

---

**Built for AthenTech · Sahasra HIS / LIS**
