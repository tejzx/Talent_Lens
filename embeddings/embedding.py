"""Sentence-transformer embeddings with a deterministic offline fallback."""
from __future__ import annotations

import functools
import hashlib
import logging

import numpy as np

log = logging.getLogger(__name__)

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
DIM = 384


@functools.lru_cache(maxsize=1)
def get_model():
    """Load MiniLM once. Returns None if the model cannot be loaded offline."""
    try:
        from sentence_transformers import SentenceTransformer

        return SentenceTransformer(MODEL_NAME)
    except Exception as exc:  # pragma: no cover - no network / no torch
        log.warning("Falling back to hashing embeddings: %s", exc)
        return None


def _hash_embed(text: str) -> np.ndarray:
    """Deterministic bag-of-words hashing vector (fallback only)."""
    vec = np.zeros(DIM, dtype="float32")
    for token in text.lower().split():
        h = int(hashlib.md5(token.encode()).hexdigest(), 16)
        vec[h % DIM] += 1.0
    return vec


def embed_texts(texts: list[str]) -> np.ndarray:
    """Return L2-normalized embeddings, shape (n, DIM)."""
    texts = [t or "" for t in texts]
    model = get_model()
    if model is not None:
        vectors = model.encode(texts, normalize_embeddings=True, convert_to_numpy=True)
        return np.asarray(vectors, dtype="float32")
    vectors = np.vstack([_hash_embed(t) for t in texts]) if texts else np.zeros((0, DIM), "float32")
    return normalize(vectors)


def embed_text(text: str) -> np.ndarray:
    return embed_texts([text])[0]


def normalize(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return (matrix / norms).astype("float32")


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    if denom == 0:
        return 0.0
    return float(np.dot(a, b) / denom)
