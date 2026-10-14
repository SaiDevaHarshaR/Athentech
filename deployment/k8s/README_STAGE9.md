# Sahasra Stage 9 - Kubernetes/K3s manifests (source only)

## What this is

A staging-only, single-replica Kustomize package for a **future Linux K3s
node**. It is not intended to be applied directly on Windows Server 2022.
Nothing in the package installs Docker, K3s, Grafana, Langfuse, Prometheus,
or Ollama. The production IIS host remains unchanged.

Files:
- `base/`: Namespace, one FastAPI Deployment, ClusterIP Service, ConfigMap,
  dedicated no-token ServiceAccount.
- `overlays/staging/`: staging customization.
- `examples/`: unconfigured Secret, optional Ingress, optional network policy,
  future Prometheus target and Ollama notes; **not deployed by Kustomize**.

## Source compatibility

- Python 3.12.7, FastAPI `main:app`, container port 8000, `/health` endpoint.
- Image `sahasra-ai-agent:py3.12.7-stage2` comes from Stage 1/2 Dockerfile.
  It must be built **for Linux/amd64** and loaded into K3s containerd or an
  approved private registry. Kubernetes doesn't build the image.
- One replica **on purpose**: current app has in-process scheduler/background
  tasks and some in-memory OTP/rate-limiting state. Never increase replicas
  before shared-state and single-runner reviews.
- `sahasra-runtime` Kubernetes Secret MUST be created privately at staging
  time. The example contains fake placeholders only. Review `config.py` for
  required vars (including mandatory Groq key assumptions) before staging.
- Admin SQL Server stays external and can write authorized AthenTech settings.
  Institution LIS database access must use genuinely read-only credentials;
  K3s itself cannot guarantee no writes. ODBC 18 TLS trust/network routing
  must be verified independently.
- No automatic AI fallback: preserve institution policy in backend. Neither
  local Ollama nor paid BYOK provider is enabled in this template.
- Windows-hosted Ollama listens on `127.0.0.1:11434` per Stage 8B. K3s Pods
  **cannot connect** to that loopback. Do not expose Ollama publicly. Bridge
  routing and authentication require separate design and approval.
- B2B OTP **test mode is off** in this staging template. Real vendor integration
  must be tested separately. Report/PDF entitlements remain app-level.

## Free-first limitations

K3s, Kustomize, Prometheus OSS, Grafana OSS, and self-hosted Langfuse OSS have
open-source distribution options. Infrastructure hardware, storage, backups,
electricity, networking, and provider SMS/WhatsApp delivery may cost money.
This Stage 9 file bundle adds **no** subscription products and does not start
any supporting observability services. Full self-hosted Langfuse needs separate
PostgreSQL, ClickHouse, Redis, and object-storage planning.

## Future source validation (do NOT run for production deployment)

With `kubectl` and Kustomize installed later:

    kubectl kustomize deployment/k8s/overlays/staging
    kubectl apply --dry-run=client -k deployment/k8s/overlays/staging

Client dry runs don't replace admission-policy or cluster checks. Run the
accompanying offline Python tests now without installing Kubernetes.

## Not production-ready until

1. Build/pullable image, Linux ODBC + Playwright smoke tests, secrets injected.
2. External SQL Server TLS/connectivity, hostname/firewall, read-only login.
3. Verified separate K3s Linux staging host with resource headroom.
4. Server-side tenant/B2B PDF authorization tests and no-fallback policy tests.
5. Confirm probes and root `health` check behavior, audit writable directories,
   optional network restrictions, persistence and backup paths.
6. Reverse-proxy/IIS cutover only after independent review. Current IIS stays.

**No installation, deployment, external connections or Windows changes made.**
