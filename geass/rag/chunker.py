"""数据源扫描、过滤与分块。"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

DEFAULT_EXTS = {
    ".md",
    ".txt",
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".csv",
    ".log",
    ".html",
    ".css",
}

MAX_FILE_SIZE = 2 * 1024 * 1024
CHUNK_SIZE = 800
CHUNK_OVERLAP = 120

_BINARY_SNIFF = 1024
_TEXT_ENCODINGS = ("utf-8", "gb18030")


def normalize_exts(exts: list[str] | tuple[str, ...] | None) -> tuple[str, ...]:
    """把用户传入的后缀归一化为小写带点元组；空则使用默认白名单。"""
    if not exts:
        return tuple(sorted(DEFAULT_EXTS))
    normalized: set[str] = set()
    for ext in exts:
        value = str(ext).strip().lower()
        if not value:
            continue
        if not value.startswith("."):
            value = "." + value
        normalized.add(value)
    return tuple(sorted(normalized))


def is_binary(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            head = handle.read(_BINARY_SNIFF)
    except OSError:
        return True
    return b"\x00" in head


def read_text_file(path: Path) -> str | None:
    """按编码顺序尝试读取；全部失败返回 None。"""
    for encoding in _TEXT_ENCODINGS:
        try:
            return path.read_text(encoding=encoding)
        except (OSError, UnicodeDecodeError):
            continue
    return None


def iter_source_files(root: Path, exts: tuple[str, ...]) -> Iterator[Path]:
    """递归列出符合后缀的文件；单文件源直接返回自身。"""
    if root.is_file():
        if _allowed(root, exts):
            yield root
        return
    if not root.is_dir():
        return
    for path in sorted(root.rglob("*")):
        if path.is_file() and _allowed(path, exts):
            yield path


def _allowed(path: Path, exts: tuple[str, ...]) -> bool:
    return path.suffix.lower() in exts


def chunk_text(
    text: str,
    size: int = CHUNK_SIZE,
    overlap: int = CHUNK_OVERLAP,
) -> list[str]:
    """按字符窗口分块，窗口结束位置尽量回退到换行符。"""
    text = text.strip()
    if not text:
        return []
    if len(text) <= size:
        return [text]

    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + size)
        if end < len(text):
            newline = text.rfind("\n", start + 1, end)
            if newline >= start + max(1, size // 2):
                end = newline + 1
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(text):
            break
        start = end - overlap
    return chunks


def chunk_file(path: Path, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP):
    """返回 ``(relative_path, chunks)``；二进制、超限或解码失败返回 None。"""
    try:
        stat = path.stat()
    except OSError:
        return None
    if stat.st_size > MAX_FILE_SIZE or is_binary(path):
        return None
    text = read_text_file(path)
    if text is None:
        return None
    return path, chunk_text(text, size=size, overlap=overlap)
