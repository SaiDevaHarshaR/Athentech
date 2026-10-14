# Sahasra AI Agent: Docker Stage 2 (Compose configuration only)

STATUS: source files only. Nothing has been installed, built or deployed.

## Files and placement

Place `Dockerfile`, `.dockerignore`, `compose.yaml`, and `.env.docker.example`
in the application repository root alongside `main.py` and `requirements.txt`.
`deployment/docker/README_STAGE2.md` is reference documentation.

This package contains Stage 1 Docker files as well, so it is a single complete
source-overlay archive. It does NOT contain application code and does not replace
any application logic, IIS files, SQL scripts or environment secrets.

## Approved decisions

- Python image: `python:3.12.7-slim-bookworm` (from Stage 1).
- Windows IIS stays the HTTPS gateway. No IIS changes in this stage.
- Existing admin and LIS SQL Server remain outside Docker.
- One FastAPI/Uvicorn worker; the current project has an in-process expiry job.
- Compose binds host TCP `127.0.0.1:18000` to container `8000` for a future proxy.
- No public API port, SQL database container, Grafana, Prometheus, Langfuse,
  Kubernetes or Hugging Face service is provisioned in Stage 2.

## Secrets and variables

Copy `.env.docker.example` to `.env.docker` privately when deployment is approved.
Compose reads `.env.docker` through `env_file`; this is separate from Compose's
interpolation `.env`. **Never publish or commit `.env.docker`.** `.dockerignore`
from Stage 1 excludes `.env.*` except `.env.example` from builds.

Mandatory source-verified names:
- `ADMIN_DB_SERVER`, `ADMIN_DB_PORT`, `ADMIN_DB_NAME`, `ADMIN_DB_USER`,
  `ADMIN_DB_PASSWORD` (`database/license_db.py`)
- `MSSQL_SERVER`, `MSSQL_DATABASE`, `MSSQL_USER`, `MSSQL_PASSWORD` (`config.py`)
- `GROQ_API_KEY` is nonoptional in uploaded `config.py`. If production code
  has since changed, reconcile with actual deployed code before any build.
- `ENCRYPTION_KEY`, `ADMIN_SECRET_KEY`, `ADMIN_PASSWORD_HASH` (`config.py`)
- `ALLOWED_ORIGINS` is comma-separated (config.py).

Do not regenerate an encryption key for the existing AthenTech admin database.
Never use an unrestricted `sa` login for client LIS. SQL permissions must be
restricted at the database level, preferably to necessary SELECT operations.

## Important compatibility constraints (unverified until staging)

1. Stage 1 Linux image installs `msodbcsql18`. The existing Python project uses
   that driver for SQL Server. SQL hostnames and network/firewall rules must be
   accessible from a Linux container; Windows localhost is not the container.
2. Some existing SQL Server code uses `TrustServerCertificate=yes`; review TLS
   policy before production deployment.
3. `main.py` has an existing `/health` endpoint. The image and Compose call it.
4. Existing code starts an expiry checker at import, so use one worker initially.
5. Chromium/Playwright dependencies from Stage 1 are unverified in a real image.
6. IIS must be configured separately to reverse proxy to the local Docker port
   only after testing; leave the existing production IIS routing untouched now.
7. On Windows, the host port's loopback behavior depends on the Docker runtime;
   verify it is truly local before any production use.
8. The source uploaded as `project.zip` is an earlier snapshot; code patches
   applied later may add required B2B, BYOK, OTP and PDF environment variables.
   Reconcile against the current production file versions before deploying.
9. The container currently has ephemeral app-writable paths, so file exports,
   audit artifacts, and imported PDF files need a reviewed persistence plan in
   a later stage. Do not route production report downloads yet.

## Preview commands (NOT executed)

```sh
# After all files are placed in app root and the private .env.docker exists:
docker compose config --quiet
docker compose build api
docker compose up -d api
docker compose ps
docker compose logs -f api
# local health check:
curl http://127.0.0.1:18000/health
```

These commands are **for the future**. No Docker installation or deployment
is part of this delivery.

## Safe rollback

Nothing changes by copying configuration files alone. If a future staged
container test fails, stop that isolated deployment and keep IIS pointing at
the original running Windows service. Avoid port conflicts with its listener.
