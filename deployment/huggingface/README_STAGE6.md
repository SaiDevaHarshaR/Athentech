# Sahasra Stage 6 — Hugging Face hosted + local (source only)

## Integration (NOT INSTALLATION)

1. This is an *additive* patch for the last working **multi-provider** BYOK version. The user-uploaded baseline `project.zip` is older; do not overwrite live `agent/llm_providers.py` with the baseline.
2. Copy `agent/hf_adapter.py`, `deployment/huggingface/` and `tests/test_stage6_huggingface.py` into a COPY of the latest Sahasra application.
3. On a COPY, run `python deployment/huggingface/apply_stage6.py`. It checks exact anchor text, refuses unfamiliar code and is idempotent. Review the diff before any eventual deployment.
4. Existing hosted Hugging Face is already in the catalog. The patch updates it to an operator-approved model override and adds **Hugging Face (Private Local Model)** as a new provider.
5. For hosted, an institution adds a Hugging Face token in its own BYOK slot and validates the chosen provider-supported model. No model availability or free quota is guaranteed.
6. For local, the operator must configure `SAHASRA_HF_LOCAL_ENABLED=1`, `SAHASRA_HF_LOCAL_CLIENT_PREFIX`, exact `SAHASRA_HF_LOCAL_BASE_URL=http://hf-local:8000/v1`, and `SAHASRA_HF_LOCAL_MODEL`. Only a single allowlisted institution may use local inference in this version. The institution must configure a BYOK API key matching the local gateway's key.
7. Local sample Compose overlay is **optional**, GPU-dependent, and not production approved. There is **no port publishing**. The operator must pin a verified vLLM image release, choose a licensed compatible model, secure secrets and verify CUDA GPU support. vLLM must not be exposed to the internet. The `ipc: host` setting needs security review before deployment.
8. Existing institution-owned slot priority/fallback logic stays intact: optional client-owned providers can be tried in order; AthenTech shared AI is never silently substituted. Unconfigured or forbidden local gateway fails closed.

## Security caveats and scope

- **Hosted** Hugging Face is an external processor; do not send PHI, raw SQL results, patient names, reports or clinical records without explicit policy, contractual and privacy review. This module does **not** implement PHI redaction for prompts or outputs.
- **Local** gateway is a shared process unless separately deployed for each tenant. This version deliberately limits the local model to one institution; do not remove that guard for a multi-tenant rollout.
- In local mode, HTTP is permitted only on the operator-defined Docker service `hf-local` within the private Compose network; this is not an internet-facing listener. The gateway API key is required, not included in the ZIP.
- No client LIS queries or writes added. The actual existing B2B/agent tool authorization must still be enforced.
- Neither mode authorizes AthenTech AI fallback. Existing checkbox controls that.
- Never expose Hugging Face tokens, gateway secrets, patient identifiers or prompt/response text in metrics or Langfuse traces.
- There is no automated model download or installation in this patch.

## Verification scope

Local unit tests prove policy behavior and adapter integration on the latest packaged BYOK source; they do not prove hosted model availability, model licenses, vLLM runtime, GPU compatibility, actual SQL Server integration, or real IIS behavior.

## Remaining operator-supplied values

| Value | Where configured | Why |
|---|---|---|
| Institution Hugging Face API token | Existing BYOK Admin AI Settings | Hosted inference authentication |
| Institution model ID | Existing BYOK slot | Chosen provider-supported model |
| `SAHASRA_HF_LOCAL_CLIENT_PREFIX` | Service private environment | Only authorized test institution |
| `SAHASRA_HF_LOCAL_MODEL` | Service private environment | Local model |
| `SAHASRA_HF_LOCAL_GATEWAY_KEY` | Service private environment and that institution's BYOK slot | Local gateway authentication |
| `HF_TOKEN` | Docker private environment | Model download authorization, where required |
| `VLLM_IMAGE_TAG` | Docker private environment | Pin reviewed compatible image |
| GPU / RAM / disk | Host requirements | Model feasibility |
