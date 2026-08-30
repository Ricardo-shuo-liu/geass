"""RAG 存储：来源元数据、同名镜像分块文件与原子写入。"""

from __future__ import annotations

import json
import os
import shutil
import threading
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class SourceMeta:
    id: str
    name: str
    root: str
    exts: tuple[str, ...]
    added_at: float
    updated_at: float
    enabled: bool = True
    mode: str = "lexical"
    embedding_model: str = ""
    embedding_dim: int = 0
    needs_reindex: bool = False
    files: dict[str, dict[str, Any]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["exts"] = list(self.exts)
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SourceMeta:
        return cls(
            id=str(data.get("id") or ""),
            name=str(data.get("name") or ""),
            root=str(data.get("root") or ""),
            exts=tuple(str(item) for item in data.get("exts") or []),
            added_at=float(data.get("added_at") or 0),
            updated_at=float(data.get("updated_at") or 0),
            enabled=bool(data.get("enabled", True)),
            mode=str(data.get("mode") or "lexical"),
            embedding_model=str(data.get("embedding_model") or ""),
            embedding_dim=int(data.get("embedding_dim") or 0),
            needs_reindex=bool(data.get("needs_reindex", False)),
            files=dict(data.get("files") or {}),
        )


class RAGStore:
    """负责 ``~/.geass/.rag`` 下的目录与文件读写。"""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def source_dir(self, source_id: str) -> Path:
        return self.root / source_id

    def index_path(self, source_id: str) -> Path:
        return self.source_dir(source_id) / "index.json"

    def load_sources(self) -> dict[str, SourceMeta]:
        sources: dict[str, SourceMeta] = {}
        for directory in sorted(self.root.iterdir()):
            if not directory.is_dir():
                continue
            index_path = directory / "index.json"
            if not index_path.is_file():
                continue
            try:
                data = json.loads(index_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(data, dict):
                meta = SourceMeta.from_dict(data)
                if meta.id:
                    sources[meta.id] = meta
        return sources

    def save_source(self, meta: SourceMeta) -> None:
        directory = self.source_dir(meta.id)
        directory.mkdir(parents=True, exist_ok=True)
        self._atomic_write_json(self.index_path(meta.id), meta.to_dict())

    def chunk_path(self, meta: SourceMeta, rel_path: str) -> Path:
        # 与原始文件同名同相对路径，只是内容为 JSON
        return self.source_dir(meta.id) / rel_path

    def load_chunks(self, meta: SourceMeta, rel_path: str) -> list[dict[str, Any]]:
        path = self.chunk_path(meta, rel_path)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        chunks = data.get("chunks") if isinstance(data, dict) else None
        return chunks if isinstance(chunks, list) else []

    def save_chunks(
        self,
        meta: SourceMeta,
        rel_path: str,
        chunks: list[dict[str, Any]],
    ) -> None:
        path = self.chunk_path(meta, rel_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self._atomic_write_json(path, {"path": rel_path, "chunks": chunks})

    def delete_chunk_file(self, meta: SourceMeta, rel_path: str) -> bool:
        path = self.chunk_path(meta, rel_path)
        try:
            path.unlink()
        except FileNotFoundError:
            return False
        return True

    def delete_source(self, source_id: str) -> bool:
        directory = self.source_dir(source_id)
        if not directory.is_dir():
            return False
        shutil.rmtree(directory, ignore_errors=True)
        return True

    def _atomic_write_json(self, path: Path, payload: dict[str, Any]) -> None:
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        try:
            os.chmod(tmp, 0o600)
        except OSError:
            pass
        os.replace(tmp, path)
