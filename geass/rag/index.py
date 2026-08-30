"""向量索引：余弦相似度；faiss 可用时自动加速，否则纯 Python。"""

from __future__ import annotations

import math
from typing import Any


def _numpy_available() -> bool:
    try:
        import numpy  # noqa: F401

        return True
    except ImportError:
        return False


def _faiss_available() -> bool:
    try:
        import faiss  # noqa: F401

        return True
    except ImportError:
        return False


def cosine_similarity(left: list[float], right: list[float]) -> float:
    """纯 Python 余弦；与向量维度无关，适用于小规模语料。"""
    dot = 0.0
    norm_left = 0.0
    norm_right = 0.0
    for a, b in zip(left, right, strict=True):
        dot += a * b
        norm_left += a * a
        norm_right += b * b
    if norm_left == 0.0 or norm_right == 0.0:
        return 0.0
    return dot / (math.sqrt(norm_left) * math.sqrt(norm_right))


class VectorIndex:
    """内存向量索引；faiss 可用且向量较多时使用近似最近邻。"""

    FAISS_THRESHOLD = 256

    def __init__(self) -> None:
        self.vectors: list[list[float]] = []
        self._faiss_index: Any = None
        self._use_faiss = _faiss_available()

    def add(self, vectors: list[list[float]]) -> None:
        if not vectors:
            return
        self.vectors.extend(vectors)
        self._faiss_index = None

    def search(self, query: list[float], limit: int = 5) -> list[tuple[int, float]]:
        if not self.vectors:
            return []
        if self._use_faiss and len(self.vectors) >= self.FAISS_THRESHOLD:
            return self._search_faiss(query, limit)
        return self._search_python(query, limit)

    def _search_python(self, query: list[float], limit: int) -> list[tuple[int, float]]:
        if _numpy_available():
            import numpy

            matrix = numpy.asarray(self.vectors, dtype="float32")
            query_array = numpy.asarray(query, dtype="float32")
            norms = numpy.linalg.norm(matrix, axis=1)
            query_norm = numpy.linalg.norm(query_array)
            if query_norm == 0:
                return []
            scores = (matrix @ query_array) / (norms * query_norm)
            order = numpy.argsort(-scores)[:limit]
            return [
                (int(index), round(float(scores[index]), 4))
                for index in order
                if float(scores[index]) > 0
            ]

        scored = [
            (index, cosine_similarity(query, vector)) for index, vector in enumerate(self.vectors)
        ]
        scored.sort(key=lambda item: item[1], reverse=True)
        return [(index, round(score, 4)) for index, score in scored[:limit] if score > 0]

    def _search_faiss(self, query: list[float], limit: int) -> list[tuple[int, float]]:
        import faiss
        import numpy

        if self._faiss_index is None:
            matrix = numpy.asarray(self.vectors, dtype="float32")
            faiss.normalize_L2(matrix)
            index = faiss.IndexFlatIP(matrix.shape[1])
            index.add(matrix)
            self._faiss_index = index
        query_array = numpy.asarray([query], dtype="float32")
        faiss.normalize_L2(query_array)
        scores, indexes = self._faiss_index.search(query_array, min(limit, len(self.vectors)))
        return [
            (int(index), round(float(score), 4))
            for index, score in zip(indexes[0], scores[0], strict=True)
            if int(index) >= 0 and float(score) > 0
        ]
