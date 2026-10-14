SAHASRA STAGE 13 -- IIS/PYTHON-ONLY METRICS + 429 DIAGNOSTIC CORRECTION
========================================================================
SOURCE-ONLY PACKAGE. NOTHING IS INSTALLED OR DEPLOYED BY THE ZIP.

User's known server layout:
  D:\Websites\P441-SahasraAiAgent\SahasraAiAgent
  Python 3.12.7 / port 8000 / Windows Server 2022

WHY THE METRICS ROUTE WAS MISSING
  The deployed main.py had not registered observability.metrics.metrics_middleware,
  even though observability/metrics.py existed. This versioned patch adds the
  registration after the app = FastAPI(...) line if not already present.

WHAT 429 ACTUALLY MEANS
  A 429 is NOT proof of daily quota exhaustion. It may indicate RPM, TPM,
  daily quota, monthly quota, or account-specific usage. This patch recognizes
  explicit "daily", "per day", "monthly", etc.; otherwise shows the honest
  ambiguous-429 message. Generic RESOURCE_EXHAUSTED no longer means "buy credits".
  The explicit no-credits/billing signals still retain their classification.
  The old unsupported "try again in a minute" promise is removed.
  If the provider gives an explicit Retry-After it remains relevant.
  Shared-AI ambiguous 429 is no longer cached for 26 hours by default;
  the unknown cooldown defaults to 300 seconds. No client BYOK policy is changed.

STAGING APPLY ONLY (PowerShell; does not install Docker/Grafana/Langfuse/Ollama):
  1. Extract this ZIP somewhere OUTSIDE production, e.g. Desktop\Stage13.
  2. Copy your LIVE Sahasra source to an isolated staging directory.
  3. In PowerShell, from the extracted Stage13 directory:
       python .\apply_stage13.py --root "D:\STAGING\SahasraAiAgent" --dry-run
       python .\apply_stage13.py --root "D:\STAGING\SahasraAiAgent"
     The script makes timestamped .bak files next to modified Python files.
     It does not overwrite an existing metrics.py.
  4. Install only the Python dependency, in the STAGING Python environment:
       python -m pip install "prometheus-client>=0.20,<1"
  5. Set in the staging service environment (do not put real tokens in Git):
       SAHASRA_METRICS_ENABLED=1
       SAHASRA_METRICS_TOKEN=<random secret at least 32 characters>
  6. Restart staging FastAPI only. On the staging host, an UNAUTHENTICATED GET
     /internal/metrics MUST return HTTP 404. With the correct bearer header it
     MUST return a Prometheus text exposition. Never publish the token or endpoint.
  7. Run synthetic offline tests first:
       python -m pytest -q tests\test_stage13_hotfix.py
     The included tests use self-contained synthetic fixtures, not live data.
  8. Once staging passes, review backups and schedule a separate controlled
     production deployment. Do not blindly overwrite B2B/BYOK files.

LANGFUSE / GRAFANA / PROMETHEUS COST AND INSTALLATION
  Grafana OSS, Prometheus OSS, and Langfuse core OSS can be self-hosted with
  no paid software subscription, but must run server processes somewhere.
  Python prometheus_client only EXPOSES metrics. It does NOT provide a Grafana
  dashboard, Prometheus scraping service, or self-hosted Langfuse server.
  Langfuse SDK alone cannot replace self-hosted Langfuse's dependencies
  (PostgreSQL, ClickHouse, Redis and object storage). Leave it disabled.
  No new software installations beyond the optional Python dependency are
  required for the metrics endpoint code.

SECURITY
  Endpoint requires a bearer token and must be blocked publicly at IIS.
  No patient names, UHIDs, phone numbers, OTPs, AI keys, client codes, report
  identifiers or prompts are placed in metric labels. New 429 errors must
  not cause unauthorized fallback to AthenTech/shared AI. No client LIS writes.
  Provider-429 classification does NOT prove whether your live key is on a
  free tier, paid tier, RPM/TPM cap, or daily quota; that requires actual
  provider dashboard and sanitized response headers.

FILES
  apply_stage13.py (safe, version-guarded patcher)
  observability/metrics.py (copy ONLY if absent in target)
  requirements.stage13.txt (pip-only dependency declaration)
  tests/test_stage13_hotfix.py (offline fixture tests)
  README_STAGE13.txt
