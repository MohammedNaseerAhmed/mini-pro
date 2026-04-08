import hashlib
import logging
import os
from typing import List, Optional

_model = None
_load_error: Optional[str] = None
logger = logging.getLogger(__name__)

# all-MiniLM-L6-v2 has a 512 WordPiece token limit.
# 400 words is a safe proxy to stay under that limit.
_MAX_WORDS = 400

# Keep model loading and inference quiet in uvicorn/Windows environments.
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")


def _truncate(text: str) -> str:
    """Truncate to _MAX_WORDS words to stay within transformer token budget."""
    words = text.split()
    if len(words) <= _MAX_WORDS:
        return text
    return " ".join(words[:_MAX_WORDS])


def _load_model_once() -> bool:
    global _model, _load_error
    if _model is not None:
        return True
    if _load_error is not None:
        return False
    try:
        from sentence_transformers import SentenceTransformer
        try:
            from transformers.utils import logging as transformers_logging
            transformers_logging.set_verbosity_error()
            disable_progress = getattr(transformers_logging, "disable_progress_bar", None)
            if callable(disable_progress):
                disable_progress()
        except Exception:
            pass
        _model = SentenceTransformer("all-MiniLM-L6-v2")
        return True
    except Exception as exc:
        _load_error = str(exc)
        logger.warning("Embedding model unavailable, using fallback embeddings: %s", exc)
        return False


def _fallback_embedding(text: str, dim: int = 384) -> List[float]:
    """Stable deterministic pseudo-embedding when model is unavailable."""
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    return [(digest[i % len(digest)] / 255.0) for i in range(dim)]


def get_embedding(text: str):
    """
    Return a 384-dim embedding list/array for text.
    Truncates to _MAX_WORDS before encoding.
    Returns None for empty input.
    Falls back to deterministic hash embedding if model is unavailable.
    """
    if not text or not text.strip():
        return None
    truncated = _truncate(text.strip())
    if _load_model_once():
        try:
            return _model.encode(truncated, show_progress_bar=False)
        except Exception as exc:
            logger.warning("Embedding encode failed, using fallback embedding: %s", exc)
    return _fallback_embedding(truncated)
