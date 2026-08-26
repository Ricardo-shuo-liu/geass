"""本地词法检索：BM25 风格打分 + 中文 n-gram。"""
from __future__ import annotations

import math
import re
from collections import Counter

_WORD_RE = re.compile(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]+")


def tokenize_terms(text: str) -> list[str]:
    """切词：ASCII 词原样小写，中文连续段额外生成双字 n-gram。"""
    terms: list[str] = []
    for part in _WORD_RE.findall(text):
        if part.isascii():
            terms.append(part.lower())
        else:
            terms.append(part)
            if len(part) >= 2:
                terms.extend(part[index : index + 2] for index in range(len(part) - 1))
    return terms


def term_counts(text: str) -> Counter:
    return Counter(tokenize_terms(text))


class LexicalIndex:
    """基于内存词频的 BM25 风格检索器。"""

    K1 = 1.5
    B = 0.75

    def __init__(self, documents: list[str]) -> None:
        self.documents = documents
        self.lengths = [len(tokenize_terms(doc)) for doc in documents]
        self.avg_len = (
            sum(self.lengths) / len(self.lengths) if self.lengths else 0.0
        )
        self.term_freqs: list[Counter] = [
            term_counts(doc) for doc in documents
        ]
        doc_count = len(documents)
        self.idf: dict[str, float] = {}
        if doc_count:
            df: Counter = Counter()
            for freqs in self.term_freqs:
                df.update(freqs.keys())
            for term, freq in df.items():
                self.idf[term] = math.log(
                    1 + (doc_count - freq + 0.5) / (freq + 0.5)
                )

    def score(self, query: str) -> list[float]:
        query_terms = set(tokenize_terms(query))
        scores: list[float] = []
        for index, freqs in enumerate(self.term_freqs):
            length = self.lengths[index] or 1
            score = 0.0
            for term in query_terms:
                tf = freqs.get(term, 0)
                if not tf:
                    continue
                denom = tf + self.K1 * (
                    1 - self.B + self.B * length / (self.avg_len or 1)
                )
                score += self.idf.get(term, 0.0) * tf / denom
            scores.append(score)
        return scores


def search_lexical(
    query: str,
    documents: list[str],
    limit: int = 5,
) -> list[tuple[int, float]]:
    """返回 ``(doc_index, normalized_score)``，按分数降序。"""
    if not documents or not query.strip():
        return []
    index = LexicalIndex(documents)
    scores = index.score(query)
    ordered = sorted(
        enumerate(scores),
        key=lambda item: item[1],
        reverse=True,
    )
    top = ordered[:limit]
    max_score = top[0][1] if top and top[0][1] > 0 else 0.0
    if max_score <= 0:
        return []
    return [(doc_index, round(score / max_score, 4)) for doc_index, score in top]
