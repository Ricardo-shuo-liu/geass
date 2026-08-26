from __future__ import annotations

from geass.rag.lexical import search_lexical, tokenize_terms


def test_tokenize_terms_handles_chinese_bigrams():
    terms = tokenize_terms("打开终端")

    assert "打开" in terms
    assert "开终" in terms
    assert "终端" in terms


def test_search_lexical_ranks_most_relevant_first():
    documents = [
        "打开终端的方法：按 ctrl+alt+t",
        "今天天气很好，适合散步",
        "终端窗口可以执行命令",
    ]

    hits = search_lexical("打开终端", documents, limit=2)

    assert hits[0][0] == 0
    assert hits[0][1] >= hits[1][1]


def test_search_lexical_empty_input():
    assert search_lexical("", ["内容"]) == []
    assert search_lexical("查询", []) == []
