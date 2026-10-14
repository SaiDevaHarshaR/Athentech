# Sahasra: free-software-first infrastructure (Stage 7B)

**No installs or deployment were done.** This overlay is a SOURCE TEMPLATE, not a complete monitoring stack; combine with the existing Stage 3/4 Prometheus and Grafana files later.

| Item | Subscription-free route | Limitations |
|---|---|---|
| Docker | Docker Engine + Compose on Linux | Docker Desktop business licensing/usage policies vary; Windows IIS cannot directly host Linux containers without a Linux host/VM. |
| Kubernetes | OSS K3s/kind/minikube/kubeadm (optional) | Complexity and RAM/CPU; leave off until needed. |
| Grafana | Grafana OSS, self-hosted | Compute, disk, backup effort. |
| Prometheus | Prometheus OSS, self-hosted | Compute, retention/storage. |
| Langfuse | Self-hosted OSS/core with license terms reviewed | PostgreSQL, ClickHouse, Redis and S3-compatible storage; significant RAM/ops. Not included in this minimal overlay. |
| Hugging Face | Download an appropriately licensed open-weight model; run locally with Ollama / llama.cpp or vLLM | Model terms vary; private models may require GPU/RAM. Hosted inference is *not* assumed free. |
| B2B intents | Stage 7B deterministic English/Telugu/Hindi matching | No token cost; supported questions only. Not a full LLM. |
| B2B OTP | Protected staging-only test flow | Real WhatsApp OTP is not free merely because software is OSS; depends on vendor/Meta terms. |

## IIS and local models
IIS is a web server / reverse proxy, **not a model runtime**. For local inference, run a model server as a separate process on the Windows host or a Linux container/VM, connected privately to Sahasra. Python 3.12.7 compatibility is not enough: evaluate RAM, CPU/GPU, available disk, and concurrency first. Prefer CPU-based *small* intent/embedding models before local large-language models.

## Free means no subscriptions, NOT zero operating cost
Server, electric power, storage, bandwidth, backups, security patching and WhatsApp authentication charges still exist. Choose Docker Engine on a licensed/approved Linux VM if avoiding Docker Desktop subscriptions is important. Review third-party model and software licenses before distributing to client institutions.

## Non-negotiable security
No raw patient text, UHIDs, phone numbers, OTPs, credentials, SQL rows or medical data in Langfuse or Prometheus. Remote hosted HF is disabled by default. Never connect local inference directly to tenant SQL or allow unrestricted SQL. Retain B2B session check, institution/organization scoping, document entitlements, BYOK, explicit fallback checkbox, read-only LIS accounts.

## Version compatibility
Never replace deployed current auth/b2b_portal.py with an older patch without merging. Stage 7B includes an isolated dispatcher to reduce churn. See README_STAGE7B.md for manual merge and validation.
