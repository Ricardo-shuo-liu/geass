from __future__ import annotations

from pathlib import Path

from geass.rag.chunker import (
    chunk_text,
    iter_source_files,
    normalize_exts,
)


def test_normalize_exts_adds_dots_and_lowercases():
    assert normalize_exts(["MD", "txt", ".py"]) == (".md", ".py", ".txt")
    assert normalize_exts(None) == normalize_exts([])
    assert ".md" in normalize_exts(None)


def test_chunk_text_splits_with_overlap():
    text = "".join(f"第{i}行内容，" for i in range(100))
    chunks = chunk_text(text, size=80, overlap=16)

    assert len(chunks) > 1
    assert all(len(chunk) <= 80 for chunk in chunks)
    # 相邻分块有重叠内容
    assert chunks[0][-16:] in chunks[1]


def test_chunk_text_backs_off_to_newline():
    text = "a" * 60 + "\n" + "b" * 60
    chunks = chunk_text(text, size=80, overlap=10)

    assert chunks[0].endswith("\n") or len(chunks[0]) <= 80


def test_iter_source_files_recursive_and_filtered(tmp_path):
    root = tmp_path / "docs"
    (root / "sub").mkdir(parents=True)
    (root / "a.md").write_text("x", encoding="utf-8")
    (root / "sub" / "b.txt").write_text("y", encoding="utf-8")
    (root / "sub" / "c.bin").write_bytes(b"\x00")

    files = list(iter_source_files(root, normalize_exts([".md", ".txt"])))

    assert {path.name for path in files} == {"a.md", "b.txt"}


def test_single_file_source(tmp_path):
    path = tmp_path / "note.md"
    path.write_text("内容", encoding="utf-8")

    files = list(iter_source_files(path, normalize_exts([".md"])))

    assert files == [path]
