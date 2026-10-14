# Sahasra Stage 5: Metadata-only Langfuse (self-hosted)

## Source compatibility
- Source baseline: uploaded project.zip (Oct 10), with follow-up BYOK/B2B patches considered.
- **Do not** copy old agent/agent.py over newer multi-provider implementation.
- Copy `observability/langfuse_tracing.py` and `observability/__init__.py` into current repository.
- Run `python deployment/langfuse/apply_stage5.py` in repository root after backup and code review.
- Append requirements.stage5.txt to requirements.txt ONLY for deployment environment later.
- Stage 3 Prometheus middleware remains independent and unchanged.

## Traces (no PHI)
- `sahasra.agent`: operation type, premium/standard mode, success, optional total token count.
- `sahasra.llm`: current provider slug (if explicitly passed), success/failure, optional numeric usage.
- `trace_business_operation`: opt-in wrapper for an already authorized B2B handler; no data payload.
- No patient identifiers, tenant names/codes, raw SQL, prompts, model responses, API keys, OTPs, phone numbers, report filenames or exception text sent.
- No LangChain/Langfuse automatic callback handlers: those can capture prompt text.
- Tracing disabled by default. Missing SDK/keys causes no app errors; tracing failure does not change app behavior.
- Actual AI-model fallback behavior remains controlled exclusively by existing BYOK code. Observability does not perform inference.

## Langfuse self-host deployment files
Langfuse v4 is **not a single-container service**. Use the official, reviewed deployment compose as a separate future stage:
https://github.com/langfuse/langfuse/blob/main/docker-compose.yml
It requires Langfuse web + worker, PostgreSQL, ClickHouse, Redis and S3-compatible object storage (e.g. MinIO), persistent volumes, secure secrets and private network access. Do not invent default secrets. Check official docs/version before deployment.
The provided `compose.langfuse.app.yaml` is an optional *Sahasra API environment overlay*, NOT a standalone running Langfuse stack.

## Configuration decisions for later
1. Approved internal Langfuse URL and network linking to Sahasra container.
2. Langfuse project keys and generated secure infrastructure secrets, privately on server.
3. TLS/access restrictions, storage/backups and retention, admin roles.
4. Data residency and healthcare privacy review before enabling traces.
5. Whether to explicitly instrument individual B2B handlers after endpoint authorization audit.

## Local-only checks (do not need Docker/Langfuse service)
`python -m unittest discover -s tests -p test_stage5_langfuse.py -v`
`python -m py_compile observability/langfuse_tracing.py deployment/langfuse/apply_stage5.py`

## Limitations
- No distributed trace context across services yet.
- No automatic per-tool observation (safe tool-name hooks can be added after authorization review).
- `current_provider` may default to unspecified in some calls and does not identify all client BYOK fallbacks automatically.
- Self-hosted Langfuse web services are documented, not installed or deployed.
- Neither clinical correctness nor live SDK exports verified by offline tests.
