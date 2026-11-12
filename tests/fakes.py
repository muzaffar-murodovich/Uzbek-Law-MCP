"""Test doubles shared by several test modules."""

import hashlib

import numpy as np

from qonunshunos.text.fts import terms


class FakeEmbedder:
    """Bag-of-terms hashed into 384 dims: deterministic, no model needed."""

    name = "fake"

    def _vec(self, text: str) -> np.ndarray:
        v = np.zeros(384, dtype=np.float32)
        for term in terms(text):
            v[int(hashlib.md5(term.encode()).hexdigest(), 16) % 384] += 1.0
        norm = np.linalg.norm(v)
        return v / norm if norm else v + 1 / np.sqrt(384)

    def passages(self, texts):
        return np.stack([self._vec(t) for t in texts]) if texts else np.zeros((0, 384))

    def query(self, text):
        return self._vec(text)


class FakeReranker:
    """Scores a text by how many query terms it contains."""

    name = "fake-reranker"

    def score(self, query, texts):
        wanted = set(terms(query))
        return [float(len(wanted & set(terms(t)))) for t in texts]
