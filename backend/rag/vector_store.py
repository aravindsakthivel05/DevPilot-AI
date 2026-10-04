"""Local NumPy cosine search with finite-vector and dimension validation."""

from typing import Protocol

import numpy as np


class VectorStore(Protocol):
    def search(self, vector: list[float], limit: int) -> list[tuple[str, float]]: ...


class LocalVectorStore:
    def __init__(self, entries):
        self.ids = [entry[0] for entry in entries]
        self.matrix = np.asarray([entry[1] for entry in entries], dtype=np.float32)
        if self.matrix.ndim != 2 or not np.isfinite(self.matrix).all():
            raise ValueError("Stored embeddings must be a finite matrix")
        norms = np.linalg.norm(self.matrix, axis=1)
        if (norms == 0).any():
            raise ValueError("Zero embeddings are invalid")
        self.matrix = self.matrix / norms[:, None]

    def search(self, vector, limit):
        query = np.asarray(vector, dtype=np.float32)
        if (
            query.shape != (self.matrix.shape[1],)
            or not np.isfinite(query).all()
            or np.linalg.norm(query) == 0
        ):
            raise ValueError("Query vector dimension/values do not match the index")
        similarities = self.matrix @ (query / np.linalg.norm(query))
        order = np.argsort(-similarities, kind="stable")[:limit]
        return [(self.ids[int(i)], float(similarities[int(i)])) for i in order]
