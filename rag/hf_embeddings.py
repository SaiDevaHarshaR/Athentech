"""Optional local Hugging Face sentence embeddings; no HTTP inference.

Stage 7A starts with safe lexical retrieval (rag.store). This module enables
future re-ranking with a locally downloaded, separately reviewed HF model.
Never auto-download models in production or upload documents to a hosted API.
"""
import os


def encode_locally(texts: list[str]):
    model_path = os.getenv('SAHASRA_RAG_HF_MODEL_PATH', '').strip()
    if not model_path:
        raise RuntimeError('Local HF embedding model path not configured')
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(model_path, local_files_only=True, trust_remote_code=False)
    return model.encode(texts, normalize_embeddings=True).tolist()
