"""FAISS-backed vector store with a NumPy fallback."""
from __future__ import annotations

import logging

import numpy as np

from .embedding import DIM, embed_texts, normalize

log = logging.getLogger(__name__)

try:  # pragma: no cover - optional dependency
    import faiss
except Exception:  # pragma: no cover
    faiss = None
    log.warning("faiss not installed; using NumPy inner-product search")


class FaissStore:
    """Inner-product index over L2-normalized vectors (== cosine similarity)."""

    def __init__(self, dim: int = DIM) -> None:
        self.dim = dim
        self.ids: list[str] = []
        self.metadata: list[dict] = []
        self._matrix = np.zeros((0, dim), dtype="float32")
        self._index = faiss.IndexFlatIP(dim) if faiss is not None else None

    def add(self, ids: list[str], texts: list[str], metadata: list[dict] | None = None) -> None:
        if not ids:
            return
        vectors = normalize(embed_texts(texts))
        self.ids.extend(ids)
        self.metadata.extend(metadata or [{} for _ in ids])
        self._matrix = np.vstack([self._matrix, vectors])
        if self._index is not None:
            self._index.add(vectors)

    def search(self, query: str, k: int = 5) -> list[tuple[str, float, dict]]:
        if not self.ids:
            return []
        k = min(k, len(self.ids))
        q = normalize(embed_texts([query]))
        if self._index is not None:
            scores, idx = self._index.search(q, k)
            pairs = zip(idx[0].tolist(), scores[0].tolist())
        else:
            sims = (self._matrix @ q[0]).tolist()
            order = sorted(range(len(sims)), key=lambda i: sims[i], reverse=True)[:k]
            pairs = ((i, sims[i]) for i in order)
        return [(self.ids[i], float(s), self.metadata[i]) for i, s in pairs if i >= 0]

    def vector_for(self, item_id: str) -> np.ndarray | None:
        if item_id not in self.ids:
            return None
        return self._matrix[self.ids.index(item_id)]

    def __len__(self) -> int:
        return len(self.ids)
