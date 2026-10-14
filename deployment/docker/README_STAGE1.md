# Sahasra Stage 1: Docker image preparation (no installation)

## Verified against uploaded project.zip (2026-10-10 archive)

- ASGI application: `main:app` using FastAPI/Uvicorn; health endpoint is `GET /health`.
- Python runtime: NOT pinned in the uploaded project. `3.11` in Dockerfile is a **build-time placeholder**. Confirm `python --version` on the existing server before building and pass that minor version using `--build-arg PYTHON_VERSION=3.xx`.
- Admin MSSQL: `database/license_db.py` explicitly requests **ODBC Driver 18 for SQL Server**.
- Client MSSQL: `database/connection.py` tries ODBC Driver 18 first; institution connections remain external.
- Reports: `reports/pdf_generator.py` launches Playwright Chromium, so container setup installs it and Linux dependencies.
- Widget and admin static files: remain in the application image. IIS still owns the public TLS/certificate and reverse-proxy settings.
- `main.py` starts an in-process expiry-checking background job at import. Use a **single worker** until scheduler ownership is revisited.

## Draft Dockerfile settings to confirm

1. `PYTHON_VERSION`: replace the example `3.11` with the Python minor version on the Windows Sahasra server. Python 3.10 will require a different base-image/OS pairing if a matching `-slim-bookworm` tag is unavailable.
2. SQL Server hostname/routing: **not entered in the image**. External `ADMIN_DB_*`, `MSSQL_*` and per-institution credentials will be injected at runtime in the later Compose stage. A Docker container must be able to route to those SQL servers.
3. TLS and ODBC 18: admin connector uses Driver 18 and driver-default TLS; client connector explicitly uses `Encrypt=no;TrustServerCertificate=yes`. Review real SQL Server encryption requirements separately. No client DB changes are made by the Dockerfile.
4. Existing settings/keys/SMTP/Redis: inject at runtime (later Compose), never bake `.env` into the image.
5. Persistent audit and export paths: need mounts/permissions at Compose stage if the app writes these directories at runtime.
6. IIS reverse proxy: no changes yet. Later proxy can forward to a port mapped to localhost on the Windows host, not expose API directly to the Internet.

## File placement (non-destructive)

Place `Dockerfile` and `.dockerignore` at the root of the current source tree (next to `main.py` and `requirements.txt`). Keep `deployment/docker/README_STAGE1.md` for instructions.

No `main.py`, `config.py`, `database/*`, `agent/*`, `auth/*` or existing IIS files are modified by this Stage 1 package.

## Next stage, NOT executed

Stage 2 will prepare `compose.yaml` and `.env.example` for a separately tested staging deployment. Do not point a not-yet-tested image at production admin SQL Server: app startup can initialize/alter admin schema and create data.

## Validation status

- Inspected uploaded project, Docker runtime dependencies and application entry point.
- Dockerfile and ignore rules checked structurally/offline.
- No Docker build, runtime smoke test, SQL Server connection, Chromium rendering or IIS deployment was attempted.
