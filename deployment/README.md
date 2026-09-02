# Sahasra AI Agent — Windows Server / IIS Deployment

This folder has everything needed to deploy on Windows Server + IIS, per
AthenTech's confirmed architecture: static files (admin panel + chat
widget) served directly by IIS, and the Python API running as a Windows
Service that IIS reverse-proxies to.

## Files in this folder

| File | What it's for |
|---|---|
| `.env.production.template` | Copy to `.env` in the project root, fill in the blanks |
| `iis-api-site/web.config` | Goes in the IIS site that fronts the API |
| `iis-static-site/web.config` | Goes in the IIS site that serves the admin panel + widget |
| `install_service.ps1` | Run once to install the API as a Windows Service |

## Questions to ask the IT admin, all in one place

Collect these before you start — every `__FILL_IN__` below maps to one of these:

1. **Domain name(s)** for the API and for the admin panel/widget (they said the office assigns this)
2. **Which port** is free on the server for the internal uvicorn process (8000 is the project default — confirm nothing else is using it)
3. **Path** where the project will actually live on the server (e.g. `C:\inetpub\SahasraAIAgent`)
4. **MSSQL server address** the API should connect to, and the login it should use
5. Where to **download/install NSSM** (or confirm it's already available) — https://nssm.cc/download
6. Confirm **ARR (Application Request Routing) + URL Rewrite** are installed in IIS — these are Microsoft's own IIS extensions, not something the project ships

## Setup order

### 1. Get the code onto the server
Copy the whole project to the path from question 3 above. Create a Python virtual environment there and `pip install -r requirements.txt`.

### 2. Fill in `.env`
Copy `.env.production.template` to `.env` in the project root (not this `deployment/` folder — the actual project root). Fill in every `__FILL_IN__`. For the admin auth values, run:
```
python auth/generate_admin_hash.py
```
and paste its output in rather than typing those by hand.

### 3. Install ARR + URL Rewrite in IIS (one-time, if not already there)
Both are free Microsoft downloads for IIS. After installing ARR, open IIS Manager → click the **server name** (top of the tree, not a specific site) → **Application Request Routing Cache** → **Server Proxy Settings** (right panel) → check **Enable proxy**. This is a server-wide setting and can't be done from a config file.

### 4. Install the API as a Windows Service
Open an **Administrator** PowerShell prompt, edit the 4 `__FILL_IN__` values at the top of `install_service.ps1`, then run it. It won't start the service automatically — that's step 6, after `.env` is confirmed correct.

### 5. Set up the two IIS sites
- **API site**: create an IIS site pointed at an empty folder (it doesn't serve real files, just proxies), bound to the API domain from question 1. Copy `iis-api-site/web.config` into that folder, replacing `__API_PORT__` with the real port from question 2.
- **Static site**: create another IIS site pointed at the project folder (or wherever you copy `admin/` and `sahasra_chat_widget.html` to), bound to the widget/admin domain. Copy `iis-static-site/web.config` into that folder.

### 6. Start the service and test
```
nssm start SahasraAIAgent
```
Then check `logs\service_stdout.log` and `logs\service_stderr.log` in the project folder for errors. If it started cleanly, test:
- `https://<api-domain>/` should return `{"message": "Sahasra AI Agent is running"}`
- `https://<api-domain>/admin/login` should respond (401 without credentials is correct — means it's reachable)

### 7. Update `ALLOWED_ORIGINS`
Once the real domains from question 1 are known, make sure `.env`'s `ALLOWED_ORIGINS` includes them exactly (scheme + domain, no trailing slash), then restart the service:
```
nssm restart SahasraAIAgent
```

## Notes

- **HTTPS**: per what you were told, SSL is already available at the office level — this likely means IIS itself terminates TLS (using a cert IIS/the office already manages), so the internal uvicorn process stays on plain HTTP on `127.0.0.1` — that's intentional and correct, don't try to also configure HTTPS inside uvicorn itself.
- **licenses.db**: still SQLite in this setup. Fine to start with, but worth revisiting if concurrent admin usage becomes heavy — flagged separately, not part of this deployment guide.
- **Logs auto-rotate** at 10MB via the NSSM config in `install_service.ps1`, so they won't grow forever unattended.
