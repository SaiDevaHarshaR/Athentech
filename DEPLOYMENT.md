# Sahasra AI Agent — Deployment Guide

Deploys the AI Agent backend, the chat widget, and the admin panel.

---

## 1. Extract the project

Unzip the deploy package to a folder on the server, e.g.:
```
C:\Athentech-main
```

---

## 2. Install Python requirements

```powershell
python -m venv venv
venv\Scripts\pip install -r requirements.txt
```

---

## 3. Install Playwright's Chromium browser

Needed for Smart Report PDF generation.

```powershell
$env:PLAYWRIGHT_BROWSERS_PATH = "C:\PlaywrightBrowsers"
venv\Scripts\python.exe -m playwright install chromium
```

---

## 4. Set up the MSSQL admin database

This is a **separate** database from the hospital data connections —
it stores institutions, licenses, admin accounts, settings, and audit
logs.

1. Create a real MSSQL database for this purpose (any name).
2. The app creates all its own tables automatically on first startup
   — no manual schema setup needed.
3. Note the server address, port, database name, username, password
   for `.env` (Step 5).

---

## 5. Add the `.env` file

Place the `.env` file (sent separately) in the project root. Confirm
it has real values for:

- `ADMIN_DB_SERVER`, `ADMIN_DB_PORT`, `ADMIN_DB_NAME`, `ADMIN_DB_USER`,
  `ADMIN_DB_PASSWORD` — the MSSQL admin database from Step 4
- `GROQ_API_KEY` and any other LLM provider keys you want available
  (`GEMINI_API_KEY`, `MISTRAL_API_KEY`, `COHERE_API_KEY`,
  `OPENROUTER_API_KEY`, `OPENAI_API_KEY`)
- `LLM_PROVIDER` — which provider to use first by default (e.g.
  `groq`); this can also be reordered later from the admin panel's
  Settings page without touching `.env` again
- `UPSTASH_REDIS_REST_URL`, `UPSTASH_REDIS_REST_TOKEN` — used for
  rate limiting, activation lockout, device lock, OTP storage, and
  provider-exhaustion tracking
- `ADMIN_USERNAME`, `ADMIN_PASSWORD_HASH`, `ADMIN_SECRET_KEY` —
  bootstrap admin login (only works while the admins table is empty;
  run `auth/generate_admin_hash.py` to generate these if needed)
- `ALLOWED_ORIGINS` — update once the real domain is known (Step 9)
- `OPENAI_ADMIN_KEY` — optional, only needed for the dashboard's
  OpenAI usage/cost tracking (separate from `OPENAI_API_KEY`, create
  at platform.openai.com/settings/organization/admin-keys)

---

## 6. Install as a Windows Service (NSSM)

**Bind to `0.0.0.0`, not `127.0.0.1`** — IIS needs to reach it, and so
does anything testing from another machine.

```powershell
nssm install SahasraAIAgent "C:\Athentech-main\venv\Scripts\python.exe" "-m uvicorn main:app --host 0.0.0.0 --port 8000"
nssm set SahasraAIAgent AppEnvironmentExtra PLAYWRIGHT_BROWSERS_PATH=C:\PlaywrightBrowsers
nssm start SahasraAIAgent
```

Open the port in Windows Firewall:
```powershell
New-NetFirewallRule -DisplayName "Sahasra AI Agent Port 8000" -Direction Inbound -LocalPort 8000 -Protocol TCP -Action Allow
```

**Confirm it's running:**
```powershell
nssm status SahasraAIAgent
Invoke-WebRequest -Uri "http://127.0.0.1:8000/" -UseBasicParsing
```
Should return `{"message": "Sahasra AI Agent is running"}`.

**If it fails to start, run it in the foreground first to see the
real error immediately** (service logs can lag or stay empty on a
startup crash):
```powershell
nssm stop SahasraAIAgent
cd C:\Athentech-main
.\venv\Scripts\python.exe -m uvicorn main:app --host 0.0.0.0 --port 8000
```

---

## 7. Two manual frontend edits (cannot come from `.env`)

Frontend JavaScript can't read server-side `.env` files, so these two
constants need a one-line edit each, specific to this server's real
public URLs:

**`widget_files/index.html`** — find and update:
```javascript
const API_URL = "http://127.0.0.1:8000/ask";
```
to the real public API URL, e.g. `https://api.athentech.in/ask`.

**`widget-loader.js`** — find and update:
```javascript
var WIDGET_URL = "https://YOUR_DOMAIN/widget_files/index.html";
```
to the real public widget URL.

---

## 8. Set up IIS

### 8a. Install IIS + required modules
- Install **IIS** (Windows feature)
- Install **Application Request Routing (ARR)**
- Install **URL Rewrite**
- Enable proxy support: IIS Manager → Server node → **Application
  Request Routing Cache** → **Server Proxy Settings** → check
  **Enable proxy**

### 8b. Site 1 — API proxy
New IIS site, empty physical folder, with a `web.config` that
reverse-proxies all requests to `http://127.0.0.1:8000`. Bind to the
API domain, e.g. `api.athentech.in`.

### 8c. Site 2 — static files (widget + admin panel)
New IIS site, physical path pointing directly at the project folder:
```
C:\Athentech-main
```
Bind to the main domain, e.g. `athentech.in`.

Resulting structure:
```
Athentech-main/
├── widget_files/
│   ├── index.html          ← the chat widget
│   └── Favicon.ico         ← used as the widget's header logo
├── admin/
│   └── index.html          ← the admin panel
├── widget-loader.js        ← floating chat bubble script
└── main.py
```

- Widget: `https://YOUR_DOMAIN/widget_files/index.html`
- Admin panel: `https://YOUR_DOMAIN/admin/index.html`
- Loader script: `https://YOUR_DOMAIN/widget-loader.js`

**Decide:** admin panel at an obvious path (`/admin/`) or a hidden,
unguessable one. Either way, same IIS site — just rename the folder.
The admin login screen is the real security; this is only about not
advertising the URL.

### 8d. Grant file permissions
Grant `IUSR` and `IIS_IUSRS` read access to the project folder
(Properties → Security → Edit → Add).

---

## 9. Point the real domain(s) at IIS

- Point the API domain at Site 1, the main domain at Site 2
- Update `.env`'s `ALLOWED_ORIGINS` to the real domain(s), remove any
  test IPs/ports
- Confirm the Step 7 edits point at these real domains, not test ones

---

## 10. Replace the Zoho widget on athentech.in

**Remove:**
```html
<script>window.$zoho=window.$zoho || {};$zoho.salesiq=$zoho.salesiq||{ready:function(){}}</script>
<script id="zsiqscript" src="https://salesiq.zoho.in/widget?wc=siq50213c50262f8727a2845b27df5b57417721448a6d67d9e14c65f8fd7ccb4b0f" defer></script>
```

**Add instead:**
```html
<script src="https://YOUR_DOMAIN/widget-loader.js" defer></script>
```

---

## 11. Final checklist

- [ ] `nssm status SahasraAIAgent` → `SERVICE_RUNNING`
- [ ] `https://api.athentech.in/` → returns the running-confirmation JSON
- [ ] `https://athentech.in/widget_files/index.html` loads the widget directly
- [ ] Admin panel login works (bootstrap credentials, or a real account)
- [ ] Create one test institution + license through the admin panel
- [ ] Activate that code in the widget, ask a real question — confirm
      a real answer comes back (not "Could not connect to the AI
      server" — if that happens, check `ALLOWED_ORIGINS` first, it's
      almost always CORS)
- [ ] Audit Logs page shows that query with a real token count
- [ ] Widget chat bubble appears on the real site via Step 10's script

---

## Known open items

- **Windows console Unicode crash**: any `print()` containing ₹ can
  crash a request on some Windows setups. Add to the very top of
  `main.py`, before other imports:
  ```python
  import sys, io
  sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
  sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
  ```
- **Emoji rendering in PDF reports**: some emoji may not render on a
  fresh Windows Server. Install Noto Color Emoji or copy
  `seguiemj.ttf` from a Windows 10/11 machine into `C:\Windows\Fonts`.
- **HIS "compare op vs ip revenue" intent**: known bug, only returns
  the OP half. Workaround: ask for OP and IP revenue separately.
- **MSSQL reserved words**: if any future code adds a new raw SQL
  column reference named `key`, `plan`, or similar reserved words,
  wrap it in brackets (`[key]`, `[plan]`) — several of these were
  found and fixed during the Turso→MSSQL migration; new code should
  watch for the same class of issue.
