from __future__ import annotations

from pathlib import Path

from geass.rag import RAGManager


class FakeProvider:
    enabled = True
    model = "fake-embed"

    def probe(self):
        return True, 3

    def embed_texts(self, texts):
        return [
            [1.0, 0.0, 0.0] if "终端" in text else [0.0, 1.0, 0.0]
            for text in texts
        ]


def make_docs(tmp_path: Path) -> Path:
    root = tmp_path / "docs"
    (root / "sub").mkdir(parents=True)
    (root / "a.md").write_text("打开终端的方法：按 ctrl+alt+t", encoding="utf-8")
    (root / "sub" / "b.txt").write_text("hello world\n" * 20, encoding="utf-8")
    (root / "skip.bin").write_bytes(b"\x00\x01")
    return root


def test_add_source_recursive_and_lexical_mode(tmp_path):
    root = make_docs(tmp_path)
    manager = RAGManager(tmp_path / ".rag")

    result = manager.add_source(root, name="docs")

    assert result["ok"] is True
    assert result["mode"] == "lexical"
    assert result["files"] == 2
    hits = manager.search("打开终端")
    assert hits and hits[0]["path"] == "a.md"


def test_add_source_vector_mode_with_provider(tmp_path):
    root = make_docs(tmp_path)
    manager = RAGManager(tmp_path / ".rag", provider=FakeProvider())

    result = manager.add_source(root, name="docs")
    hits = manager.search("打开终端", limit=1)

    assert result["mode"] == "vector"
    assert hits[0]["mode"] == "vector"
    assert hits[0]["path"] == "a.md"
    assert hits[0]["score"] > 0.9


def test_reimport_reconciles_removed_file(tmp_path):
    root = make_docs(tmp_path)
    manager = RAGManager(tmp_path / ".rag")
    manager.add_source(root, name="docs")

    assert manager.remove_file("docs", "a.md") is True
    summary = manager.list_sources()[0]
    assert summary["files"] == 1
    meta = manager._find_source("docs")
    assert "a.md" not in meta.files
    assert not (manager.store.source_dir(meta.id) / "a.md").exists()

    manager.add_source(root, name="docs")
    summary = manager.list_sources()[0]

    assert summary["files"] == 2
    assert summary["chunks"] == 2


def test_enable_disable_source(tmp_path):
    root = make_docs(tmp_path)
    manager = RAGManager(tmp_path / ".rag")
    manager.add_source(root, name="docs")

    assert manager.set_enabled("docs", False) is True
    assert manager.search("打开终端") == []
    assert manager.set_enabled("docs", True) is True
    assert manager.search("打开终端")


def test_fingerprint_mismatch_marks_needs_reindex(tmp_path):
    root = make_docs(tmp_path)
    RAGManager(tmp_path / ".rag", provider=FakeProvider()).add_source(
        root, name="docs"
    )

    class OtherProvider(FakeProvider):
        model = "other-embed"

    manager = RAGManager(tmp_path / ".rag", provider=OtherProvider())
    summary = manager.list_sources()[0]

    assert summary["needs_reindex"] is True
    # 指纹不匹配时检索自动走词法
    hits = manager.search("打开终端")
    assert hits and hits[0]["mode"] == "lexical"

    result = manager.reindex("docs")
    assert result["mode"] == "vector"
    assert manager.list_sources()[0]["needs_reindex"] is False


def test_context_for_respects_min_score(tmp_path):
    root = make_docs(tmp_path)
    manager = RAGManager(tmp_path / ".rag")
    manager.add_source(root, name="docs")

    context = manager.context_for(
        "完全不相关的内容", limit=5, max_chars=500, min_score=0.6
    )
    assert context == ""

    context = manager.context_for(
        "打开终端", limit=5, max_chars=500, min_score=0.1
    )
    assert "打开终端" in context


def test_remove_source(tmp_path):
    root = make_docs(tmp_path)
    manager = RAGManager(tmp_path / ".rag")
    manager.add_source(root, name="docs")

    assert manager.remove_source("docs") is True
    assert manager.list_sources() == []
    assert manager.remove_source("docs") is False


def test_set_all_enabled(tmp_path):
    root = make_docs(tmp_path)
    manager = RAGManager(tmp_path / ".rag")
    manager.add_source(root, name="docs")
    root2 = tmp_path / "docs2"
    root2.mkdir()
    (root2 / "x.md").write_text("另一份文档", encoding="utf-8")
    manager.add_source(root2, name="docs-2")

    assert manager.set_all_enabled(False) == 2
    assert manager.search("打开终端") == []
    assert manager.set_all_enabled(True) == 2
    assert manager.search("打开终端")
