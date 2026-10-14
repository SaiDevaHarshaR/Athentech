# Stage 3 - Privacy-safe Prometheus observability (source only)

Scope: Sahasra FastAPI + existing IIS gateway + **external SQL Server**. No Grafana,
Prometheus, Langfuse, Kubernetes or Hugging Face service is installed or started.

## Files and how to merge with the CURRENT application

This package combines Stage 1/2 Docker source files with the new Stage 3 files.
The uploaded `project.zip` is older than several recent BYOK and B2B patches:
DO NOT overwrite your live main.py, B2B router, AI adapters, IIS config or SQL files.

1. Copy `observability/__init__.py`, `observability/metrics.py` into existing app.
2. Review `patches/main.py.patch` then run:
   `python deployment/docker/apply_stage3.py` **from your app root**.
   This adds one FastAPI middleware and adds `prometheus-client` requirement.
   Keep a backup and inspect the diff. This script does not install dependencies.
3. Keep the Dockerfile, `.dockerignore`, `compose.yaml`, `.env.docker.example` as
   source templates; use them when Docker is installed in a later stage.
4. `deployment/prometheus/prometheus.yml` is a future Prometheus scrape template.
   `sahasra-api:8000` resolves only on the same Docker network. Stage 2 currently
   does not start a Prometheus service or connect it to a network.
5. Metrics are **OFF** by default. To enable in private staging, configure
   `SAHASRA_METRICS_ENABLED=1`, `SAHASRA_METRICS_TOKEN=<32+ random characters>`.
   `/internal/metrics` requires an Authorization Bearer token; without both
   settings it returns 404. Configure your IIS reverse proxy to **block public
   access to /internal/metrics** as well. Do not embed the token in source or logs.
6. When Prometheus is deployed later, mount a secret token file into Prometheus
   at `/etc/prometheus/secrets/sahasra_metrics_token` and make it match the
   Sahasra service token. Do not commit the token or service credentials.

## What is actually instrumented

- All FastAPI requests: totals and latency by **coarse, fixed route category**;
  method and status class only. No IP, URL query, patient, bill, chat content,
  phone, institution identifier or activation code in metric labels.
- B2B API request counters: OTP request/verify endpoint HTTP status classes,
  business chat, overview, bills, report download, logout. HTTP 200 on an OTP
  request does **not** mean an SMS was sent; it may intentionally return 200 for
  unregistered numbers. Do not treat request metrics as actual delivery stats.
- Report request timing for PDF and Excel endpoints. Measures API duration,
  not strictly PDF generation duration.
- Provider and OTP **outcome** counters: safe explicit functions exist but are
  **not automatically wired** to adapter implementations, since the uploaded
  project.zip doesn't include the latest multi-provider/B2B sources. Integration
  requires placing hooks in the **real** provider and OTP backends after results
  are known. Their counters remain zero until hooked.

## Integration hook examples (for code review only)

In your real provider adapter after an actual provider call completes:

```python
from observability.metrics import record_ai_provider
record_ai_provider(provider='groq', result='success', elapsed_seconds=0.37)
# Use result='error' / 'timeout' / 'rate_limited' / 'quota_exhausted'
# as applicable; never add key, model output, query, patient or tenant labels.
```

In the real B2B verification backend **after** successful OTP verification:

```python
from observability.metrics import record_b2b_otp_outcome
record_b2b_otp_outcome('verify', 'success')
```

Failure outcomes and send results must also be recorded in the appropriate
backend branch; do not infer them from HTTP 200. Preserve the rule that
all production OTP verification must fail closed.

## Security and compatibility

- Does not change BYOK provider selection or fallback consent.
- Does not query or write client LIS databases.
- Does not capture HTTP request/response bodies or logs.
- Avoids high-cardinality labels to protect patient privacy and Prometheus.
- Metrics stored in-process; Stage 2 uses a single Uvicorn worker. If switching
  to multiple workers later, use an appropriate multiprocess metrics strategy.
- Existing `security_middleware` continues enforcing its normal rate limits.
- Existing `/health` may include exception descriptions; do not expose them in
  Prometheus. This patch does not change `/health` behavior.

## Offline checks (no Docker installation)

In an environment with `pytest` and `prometheus-client` installed:

`python -m pytest -q tests/test_stage3_metrics.py`

The delivered tests use the metrics module independently; live IIS, SQL Server,
Windows-to-Linux connection, browser, and real provider/OTP tests are pending.
