import logging
from typing import Optional

import numpy as np

from backend.ai.embeddings import get_embedding

logger = logging.getLogger(__name__)

try:
    import faiss
except Exception:
    faiss = None


class VectorStore:
    def __init__(self, dim: int = 384) -> None:
        self.dim = dim
        self.index = faiss.IndexFlatL2(dim) if faiss is not None else None
        self.vectors = []       # fallback when faiss unavailable
        self.case_ids = []      # parallel list of case_number strings

    def add_case(self, case_id: str, text: str) -> None:
        emb = get_embedding(text)
        if emb is None:
            return
        vec = np.array([emb], dtype="float32")
        if self.index is not None:
            self.index.add(vec)
        else:
            self.vectors.append(vec[0])
        self.case_ids.append(case_id)

    def search(self, text: str, k: int = 5):
        emb = get_embedding(text)
        if emb is None:
            return []
        vec = np.array([emb], dtype="float32")

        if self.index is not None and len(self.case_ids) > 0:
            _, I = self.index.search(vec, min(k, len(self.case_ids)))
            indices = [int(i) for i in I[0]]        # cast np.intp → int
        elif self.vectors:
            query = vec[0]
            dists = [float(np.linalg.norm(query - v)) for v in self.vectors]
            indices = [int(i) for i in np.argsort(dists)[:k]]
        else:
            return []

        return [self.case_ids[i] for i in indices if 0 <= i < len(self.case_ids)]

    def load_from_db(self, db=None) -> int:
        """
        Re-load all previously embedded case chunks from MongoDB into this
        in-memory index.  Called once at startup so search works across
        server restarts.

        Returns the number of chunks loaded.
        """
        if db is None:
            try:
                from backend.database.mongo import get_db
                db = get_db()
            except Exception as exc:
                logger.warning("VectorStore.load_from_db: cannot connect to DB — %s", exc)
                return 0

        loaded = 0
        try:
            # Use case_chunks collection (text + case_number stored by pipeline)
            cursor = db["case_chunks"].find(
                {}, {"case_number": 1, "text": 1}, no_cursor_timeout=False
            )
            for chunk in cursor:
                cn   = chunk.get("case_number")
                text = chunk.get("text", "")
                if not cn or not text:
                    continue
                # Only add if this case_number not already in index
                if cn in self.case_ids:
                    continue
                emb = get_embedding(text)
                if emb is None:
                    continue
                vec = np.array([emb], dtype="float32")
                if self.index is not None:
                    self.index.add(vec)
                else:
                    self.vectors.append(vec[0])
                self.case_ids.append(cn)
                loaded += 1
        except Exception as exc:
            logger.warning("VectorStore.load_from_db: error during reload — %s", exc)

        logger.info("VectorStore loaded %d chunks from MongoDB.", loaded)
        return loaded


# Global singleton — populated at startup by main.py lifespan or app startup event
vector_store = VectorStore()
