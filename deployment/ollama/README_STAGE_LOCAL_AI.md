# Sahasra local CPU AI — source-only stage

**No installation, download, deployment or IIS changes performed.** Based on the provided multi-provider BYOK source; apply as a reviewable diff against your running version, not as a blind overwrite.

## Files
- `agent/ollama_local.py`: localhost-only model endpoint; explicit environment allowlist.
- `agent/llm_providers.py`: local model support and fail-closed policy; no external token.
- `auth/institution_ai_slots.py`: institution-local opt-in provider cards without keys.
- `admin/app.js`: local provider display and readiness check.
- `deployment/ollama/.env.local-ai.example`: placeholder-only configuration.
- `tests/test_local_ollama.py`: local policy and source integration tests.

## Windows Server 2022 target
- Keep existing IIS website and FastAPI service operational. Run Ollama as a **separate process**, on loopback port 11434, when deployment is approved. Do not host models *in IIS*.
- Qwen3 4B (`qwen3:4b`) first; Qwen3 8B (`qwen3:8b`) is optional. No GPU needed, but CPU throughput, memory usage and Windows Server runtime support must be verified in staging.
- The default example disables Ollama; enabling requires both `SAHASRA_OLLAMA_ENABLED=1` and comma-separated institution prefixes in `SAHASRA_OLLAMA_ALLOWED_INSTITUTIONS`, plus selecting **Local Ollama** in each institution's AI Settings.
- No per-institution API key is generated or stored for the local option. The existing admin SQL Server BYOK slots table records selection only.
- Shared AthenTech AI is never invoked as a substitute for failed configured local model.
- For Stage 2 Linux Docker migration, loopback inside the container is NOT the Windows host. Use a vetted authenticated internal gateway and update the pinned endpoint policy only after reviewing network isolation. No bridge override is silently provided here.
- The local model is shared compute; it **does not** provide separate memory/context per institution automatically. Chat state, RAG retrieval, SQL and B2B authorization must remain tenant-scoped in Sahasra.
- Metadata-only telemetry remains unchanged. The local inference request itself may contain authorized content; server operators must protect process logs and model endpoint.
- **No additional subscription fees**, but hardware/power/operational costs apply. Model licensing must be checked for your deployment.
- The B2B intent stage remains restricted to approved actions. Do not let LLM output generate or execute SQL or authorize PDF downloads.

## Staging later (not executed)
1. Back up current app and admin DB; compare files.
2. Verify supported Windows Server runtime and CPU load budget.
3. Install Ollama separately and pull model(s) only after permission.
4. Configure loopback-only listening, set environment allowlist and enable policy; restart Sahasra.
5. Open Institution Registry > AI Settings > Local Ollama, choose `qwen3:4b`, save, recheck.
6. Run one institution allowed / another denied / model unavailable / fallback checkbox off / B2B OTP invalid tests.
7. Benchmark latency/concurrency and SQL Server impact; keep prod untouched until signed off.

## Scope
This is **source preparation**, not a production certification. Source is derived from the last supplied multi-provider patch, not live IIS files. The existing `database/license_db.py`, `main.py`, clinical report code and database schemas are not replaced.
