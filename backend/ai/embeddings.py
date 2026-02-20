import hashlib
from typing import Optional

_model = None
_load_error: Optional[str] = None


def _load_model_once() -> bool:
    global _model, _load_error
    if _model is not None:
        return True
    if _load_error is not None:
        return False
    try:
        from sentence_transformers import SentenceTransformer

        _model = SentenceTransformer("all-MiniLM-L6-v2")
        return True
    except Exception as exc:
        _load_error = str(exc)
        return False


def _fallback_embedding(text: str, dim: int = 384):
    # Stable deterministic pseudo-embedding when model is unavailable.
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    values = [(digest[i % len(digest)] / 255.0) for i in range(dim)]
    return values


def get_embedding(text: str):
    if text is None or len(text.strip()) == 0:
        return None
    if _load_model_once():
        return _model.encode(text)
    return _fallback_embedding(text)
