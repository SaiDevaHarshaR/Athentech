# Sahasra Stage 7A — Approved Knowledge RAG (source-only)

## Scope
- B2C: **opt-in** retrieval of *manually reviewed and approved* service/FAQ documents, separated by institution prefix. Existing White Label `b2c_knowledge` is retained. No AI-generated SQL.
- B2B: **session-gated helper only**. `rag.b2b_gateway.approved_b2b_context` requires a verified, server-constructed B2B context and organization code. It is NOT connected to the B2B router yet, because the live post-patch B2B authorization code has not been provided and cannot safely be guessed. Nothing here exposes a public retrieval route.
- Hugging Face: optional **offline/local** sentence-transformers interface for a separately approved local model. It is intentionally not in the request path yet. Stage 7A retrieval uses no external embedding API, so no contents are sent to Hugging Face or Langfuse.

## Files
- `rag/store.py`: scoped immutable-ish JSON document store with lexical chunk retrieval and reference excerpts.
- `rag/b2b_gateway.py`: strict B2B verified-session retrieval helper.
- `rag/hf_embeddings.py`: optional no-network local embedding module (requires separate dependency and model file).
- `deployment/rag/ingest_approved.py`: offline admin-only .txt/.md ingestion, **not a public endpoint**.
- `deployment/rag/apply_stage7a.py`: idempotent B2C-only patch for `auth/whitelabel.py`; refuses incompatible revisions.
- `tests/test_stage7a_rag.py`: offline unit tests.

## Decisions / placeholders to be confirmed BEFORE staging
1. `SAHASRA_RAG_STORE`: private persistent folder mounted outside `/app`, IIS static content, and any client LIS folder. Set owner-only permissions and encrypted storage/backups as appropriate.
2. Reviewed document list: public FAQs / locations / hours / test preparation instructions that the lab explicitly authorizes. **Never ingest patient reports, LIS exports, UHIDs, personal data, passwords, tokens or raw patient results.** Automatic PHI detection is NOT provided.
3. Verified institution prefixes and (later) B2B corporate codes from authoritative backend records.
4. Hugging Face embedding model choice and license: not selected; do not auto-download a model.
5. B2C AI provider routing still follows your installed `auth/whitelabel.py` version. This patch **does not change** BYOK choices or opt-in shared fallback. Confirm their behavior independently before public usage.

## Apply to a copy of production source (NOT live)
Extract package at project root and inspect changes. Set `SAHASRA_RAG_ENABLED=0` initially.

```sh
python deployment/rag/apply_stage7a.py /path/to/copy-of-sahasra
python -m pytest -q tests/test_stage7a_rag.py
```

Example ingestion after human review:
```sh
export SAHASRA_RAG_STORE=/private/path/rag
python -m deployment.rag.ingest_approved --institution KLIS --audience b2c --file reviewed_faq.txt --title 'KLIS Public FAQ' --approver 'authorized-admin'
```
B2B examples require `--audience b2b --organization ORG_CODE` and must never use a client organization supplied by the browser as an authorization proof.

When activating in staging: set `SAHASRA_RAG_ENABLED=1` **only** after reviewing the exact patched B2C source and approved content. Existing RAG files are local to the application host; deploying multiple replicas requires an approved shared or replicated document storage strategy.

## Behavior and limits
- Relevant excerpts are provided to the existing B2C answer generator as *untrusted reference text*. Prompt injection remains a risk; only approved materials are permitted.
- When no match is found, existing B2C knowledge flow remains unchanged; no documents from other institutions are searched.
- No AI provider key is used for retrieval. A subsequent LLM response still uses whichever provider the app currently authorizes; this is not a new fallback.
- Metrics/trace payloads are not added by Stage 7A. Do not include retrieved excerpts or patient data in telemetry.
- Not suitable for clinical diagnosis, medical-report interpretation, or individual patient downloads.
- Keyword-based retrieval is a safe baseline, not a fully semantic multilingual vector search. The optional HF module is a future enhancement.
- Admin-only ingestion and private storage must be enforced by host permissions; index files are not encrypted by this module. Use volume encryption if storing sensitive business documents.
- **No installation, Docker build, Hugging Face inference, live SQL Server testing, or IIS deployment has been performed.**
