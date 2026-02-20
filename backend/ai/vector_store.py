import numpy as np
from backend.ai.embeddings import get_embedding

try:
    import faiss
except Exception:
    faiss = None


class VectorStore:
    def __init__(self, dim=384):
        self.index = faiss.IndexFlatL2(dim) if faiss is not None else None
        self.vectors = []
        self.case_ids = []

    def add_case(self, case_id, text):
        emb = get_embedding(text)
        if emb is None:
            return
        emb = np.array([emb]).astype("float32")
        if self.index is not None:
            self.index.add(emb)
        else:
            self.vectors.append(emb[0])
        self.case_ids.append(case_id)

    def search(self, text, k=5):
        emb = get_embedding(text)
        if emb is None:
            return []
        emb = np.array([emb]).astype("float32")
        if self.index is not None and len(self.case_ids) > 0:
            _, I = self.index.search(emb, min(k, len(self.case_ids)))
            indices = I[0]
        else:
            if not self.vectors:
                return []
            query = emb[0]
            dists = [float(np.linalg.norm(query - v)) for v in self.vectors]
            indices = np.argsort(dists)[:k]

        results = []
        for idx in indices:
            if idx < len(self.case_ids):
                results.append(self.case_ids[idx])

        return results


# global instance
vector_store = VectorStore()
