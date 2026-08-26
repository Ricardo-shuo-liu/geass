from __future__ import annotations

from geass.rag.index import VectorIndex, cosine_similarity


def test_cosine_similarity():
    assert cosine_similarity([1, 0], [1, 0]) == 1.0
    assert cosine_similarity([1, 0], [0, 1]) == 0.0


def test_vector_index_returns_top_k():
    index = VectorIndex()
    index.add([[1, 0, 0], [0, 1, 0], [1, 1, 0]])

    hits = index.search([1, 0, 0], limit=2)

    assert hits[0][0] == 0
    assert len(hits) == 2
