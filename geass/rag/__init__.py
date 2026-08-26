"""RAG 数据源接入与检索增强。"""
from __future__ import annotations

import os
import re
import threading
import time
from pathlib import Path
from typing import Any

from .chunker import (
    chunk_file,
    iter_source_files,
    normalize_exts,
)
from .embeddings import EmbeddingProvider
from .index import VectorIndex
from .lexical import search_lexical
from .store import RAGStore, SourceMeta


def default_rag_path() -> Path:
    home = Path(os.environ.get("GEASS_HOME", str(Path.home())))
    return home / ".geass" / ".rag"


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower().strip()).strip("-")
    return slug[:48].rstrip("-") or "source"


class RAGManager:
    """RAG 对外入口：导入、检索、注入上下文与数据源管理。"""

    def __init__(
        self,
        path: str | Path | None = None,
        provider: EmbeddingProvider | None = None,
    ) -> None:
        self.provider = provider
        self.store = RAGStore(path or default_rag_path())
        self._lock = threading.RLock()
        self._sources: dict[str, SourceMeta] = self.store.load_sources()
        self._probe: tuple[bool, int] | None = None
        self._chunk_cache: dict[str, tuple[tuple[Any, ...], list[dict[str, Any]]]] = {}
        self._refresh_loaded_modes()

    def _refresh_loaded_modes(self) -> None:
        ok, _dim = self._probe_embedding()
        changed = False
        for meta in self._sources.values():
            if meta.mode == "vector" and (
                not ok
                or self.provider is None
                or meta.embedding_model != self.provider.model
            ):
                meta.needs_reindex = True
                changed = True
        if changed:
            for meta in self._sources.values():
                if meta.needs_reindex:
                    self.store.save_source(meta)

    def _probe_embedding(self) -> tuple[bool, int]:
        if self.provider is None or not self.provider.enabled:
            return False, 0
        if self._probe is None:
            self._probe = self.provider.probe()
        return self._probe

    def _find_source(self, name_or_id: str) -> SourceMeta | None:
        key = str(name_or_id or "").strip()
        if not key:
            return None
        if key in self._sources:
            return self._sources[key]
        for meta in self._sources.values():
            if meta.name == key:
                return meta
        return None

    def list_sources(self) -> list[dict[str, Any]]:
        with self._lock:
            sources = list(self._sources.values())
        return [
            {
                "id": meta.id,
                "name": meta.name,
                "root": meta.root,
                "exts": list(meta.exts),
                "enabled": meta.enabled,
                "mode": meta.mode,
                "needs_reindex": meta.needs_reindex,
                "embedding_model": meta.embedding_model,
                "embedding_dim": meta.embedding_dim,
                "files": len(meta.files),
                "chunks": sum(
                    int(entry.get("chunks") or 0)
                    for entry in meta.files.values()
                ),
            }
            for meta in sorted(sources, key=lambda item: item.name)
        ]

    def add_source(
        self,
        path: str | Path,
        name: str | None = None,
        exts: list[str] | tuple[str, ...] | None = None,
    ) -> dict[str, Any]:
        source_path = Path(path).expanduser().resolve()
        if not source_path.exists():
            raise ValueError(f"数据源不存在：{source_path}")

        exts = normalize_exts(exts)
        if source_path.is_file():
            root = source_path.parent
            rel_files = [source_path.name]
            default_name = source_path.stem
        elif source_path.is_dir():
            root = source_path
            rel_files = sorted(
                item.relative_to(root).as_posix()
                for item in iter_source_files(root, exts)
            )
            default_name = root.name
        else:
            raise ValueError("数据源必须是文件或文件夹")

        with self._lock:
            existing = next(
                (
                    meta
                    for meta in self._sources.values()
                    if Path(meta.root).resolve() == root
                ),
                None,
            )
            if existing is not None:
                meta = existing
                base_id = meta.id
            else:
                base_id = _slugify(name or default_name)
                candidate = base_id
                index = 2
                while candidate in self._sources:
                    candidate = f"{base_id}-{index}"
                    index += 1
                meta = SourceMeta(
                    id=candidate,
                    name=str(name or default_name).strip() or candidate,
                    root=str(root),
                    exts=exts,
                    added_at=time.time(),
                    updated_at=time.time(),
                )

            ok, dim = self._probe_embedding()
            vector_mode = bool(ok and dim)
            meta.exts = exts
            meta.updated_at = time.time()
            meta.mode = "vector" if vector_mode else "lexical"
            meta.embedding_model = (
                self.provider.model if vector_mode and self.provider else ""
            )
            meta.embedding_dim = dim if vector_mode else 0
            meta.needs_reindex = False

            old_files = dict(meta.files)
            new_files: dict[str, dict[str, Any]] = {}
            pending_embed: list[tuple[str, int, str]] = []

            for rel in rel_files:
                file_path = root / rel
                try:
                    stat = file_path.stat()
                except OSError:
                    continue
                previous = old_files.get(rel)
                keep = (
                    previous is not None
                    and int(previous.get("size") or 0) == stat.st_size
                    and float(previous.get("mtime") or 0) == stat.st_mtime
                    and meta.mode == previous.get("mode", meta.mode)
                )
                if keep:
                    new_files[rel] = {
                        "size": stat.st_size,
                        "mtime": stat.st_mtime,
                        "chunks": int(previous.get("chunks") or 0),
                        "mode": meta.mode,
                    }
                    continue
                result = chunk_file(file_path)
                if result is None:
                    continue
                _, chunks_text = result
                chunks: list[dict[str, Any]] = [
                    {"index": index, "text": text, "embedding": None}
                    for index, text in enumerate(chunks_text)
                ]
                if vector_mode:
                    pending_embed.extend(
                        (rel, chunk["index"], chunk["text"])
                        for chunk in chunks
                    )
                new_files[rel] = {
                    "size": stat.st_size,
                    "mtime": stat.st_mtime,
                    "chunks": len(chunks),
                    "mode": meta.mode,
                }
                self.store.save_chunks(meta, rel, chunks)

            if vector_mode and pending_embed:
                texts = [item[2] for item in pending_embed]
                vectors = self.provider.embed_texts(texts)
                by_rel: dict[str, dict[int, list[float]]] = {}
                for (rel, chunk_index, _text), vector in zip(
                    pending_embed, vectors
                ):
                    by_rel.setdefault(rel, {})[chunk_index] = vector
                for rel, mapping in by_rel.items():
                    chunks = self.store.load_chunks(meta, rel)
                    for chunk in chunks:
                        vector = mapping.get(chunk.get("index"))
                        if vector is not None:
                            chunk["embedding"] = vector
                    self.store.save_chunks(meta, rel, chunks)

            for rel in list(old_files):
                if rel not in new_files:
                    self.store.delete_chunk_file(meta, rel)

            meta.files = new_files
            meta.updated_at = time.time()
            self.store.save_source(meta)
            self._sources[meta.id] = meta
            self._chunk_cache.pop(meta.id, None)

        return {
            "ok": True,
            "id": meta.id,
            "name": meta.name,
            "mode": meta.mode,
            "files": len(meta.files),
            "chunks": sum(
                int(entry.get("chunks") or 0) for entry in meta.files.values()
            ),
            "message": (
                f"已锁定数据源「{meta.name}」"
                f"（{meta.mode}模式，{len(meta.files)} 个文件）"
            ),
        }

    def remove_source(self, name_or_id: str) -> bool:
        with self._lock:
            meta = self._find_source(name_or_id)
            if meta is None:
                return False
            removed = self.store.delete_source(meta.id)
            if removed:
                self._sources.pop(meta.id, None)
                self._chunk_cache.pop(meta.id, None)
            return removed

    def remove_file(self, name_or_id: str, rel_path: str) -> bool:
        rel_path = str(rel_path or "").strip().replace("\\", "/").lstrip("/")
        with self._lock:
            meta = self._find_source(name_or_id)
            if meta is None or rel_path not in meta.files:
                return False
            self.store.delete_chunk_file(meta, rel_path)
            del meta.files[rel_path]
            meta.updated_at = time.time()
            self.store.save_source(meta)
            self._chunk_cache.pop(meta.id, None)
            return True

    def set_enabled(self, name_or_id: str, enabled: bool) -> bool:
        with self._lock:
            meta = self._find_source(name_or_id)
            if meta is None:
                return False
            meta.enabled = bool(enabled)
            meta.updated_at = time.time()
            self.store.save_source(meta)
            self._chunk_cache.pop(meta.id, None)
            return True

    def set_all_enabled(self, enabled: bool) -> int:
        """批量启用/停用全部数据源，返回被改动的数量。"""
        changed = 0
        with self._lock:
            for meta in list(self._sources.values()):
                if meta.enabled == bool(enabled):
                    continue
                meta.enabled = bool(enabled)
                meta.updated_at = time.time()
                self.store.save_source(meta)
                self._chunk_cache.pop(meta.id, None)
                changed += 1
        return changed

    def reindex(self, name_or_id: str) -> dict[str, Any]:
        with self._lock:
            meta = self._find_source(name_or_id)
            if meta is None:
                return {"ok": False, "error": "数据源不存在"}
            ok, dim = self._probe_embedding()
            vector_mode = bool(ok and dim)
            meta.mode = "vector" if vector_mode else "lexical"
            meta.embedding_model = (
                self.provider.model if vector_mode and self.provider else ""
            )
            meta.embedding_dim = dim if vector_mode else 0
            meta.needs_reindex = False

            texts_by_rel: dict[str, list[str]] = {}
            for rel in list(meta.files):
                chunks = self.store.load_chunks(meta, rel)
                texts_by_rel[rel] = []
                for chunk in chunks:
                    text = str(chunk.get("text") or "")
                    if text:
                        texts_by_rel[rel].append(text)
                        chunk["embedding"] = None
                self.store.save_chunks(meta, rel, chunks)

            if vector_mode:
                for rel, texts in texts_by_rel.items():
                    if not texts:
                        continue
                    vectors = self.provider.embed_texts(texts)
                    chunks = self.store.load_chunks(meta, rel)
                    position = 0
                    for chunk in chunks:
                        if str(chunk.get("text") or ""):
                            chunk["embedding"] = vectors[position]
                            position += 1
                    self.store.save_chunks(meta, rel, chunks)

            meta.updated_at = time.time()
            self.store.save_source(meta)
            self._chunk_cache.pop(meta.id, None)
            return {
                "ok": True,
                "mode": meta.mode,
                "message": f"已重建「{meta.name}」索引（{meta.mode}模式）",
            }

    def _chunks_for_source(self, meta: SourceMeta) -> list[dict[str, Any]]:
        key = (meta.updated_at, meta.mode, meta.needs_reindex)
        cached = self._chunk_cache.get(meta.id)
        if cached is not None and cached[0] == key:
            return cached[1]
        chunks: list[dict[str, Any]] = []
        for rel in sorted(meta.files):
            for chunk in self.store.load_chunks(meta, rel):
                chunks.append(
                    {
                        "source": meta.id,
                        "source_name": meta.name,
                        "path": rel,
                        "index": int(chunk.get("index") or 0),
                        "text": str(chunk.get("text") or ""),
                        "embedding": chunk.get("embedding"),
                    }
                )
        self._chunk_cache[meta.id] = (key, chunks)
        return chunks

    def search(
        self,
        query: str,
        source: str | None = None,
        limit: int = 5,
        min_score: float | None = None,
    ) -> list[dict[str, Any]]:
        query = str(query or "").strip()
        if not query:
            return []
        with self._lock:
            metas = list(self._sources.values())
        if source:
            with self._lock:
                filtered = self._find_source(source)
            metas = [filtered] if filtered is not None else []

        ok, _dim = self._probe_embedding()
        hits: list[dict[str, Any]] = []
        for meta in metas:
            if not meta.enabled:
                continue
            chunks = self._chunks_for_source(meta)
            if not chunks:
                continue
            if meta.mode == "vector" and ok and not meta.needs_reindex:
                try:
                    vector = self.provider.embed_texts([query])[0]
                    index = VectorIndex()
                    index.add(
                        [chunk["embedding"] for chunk in chunks if chunk.get("embedding")]
                    )
                    vectors_map = [
                        (position, chunk)
                        for position, chunk in enumerate(chunks)
                        if chunk.get("embedding")
                    ]
                    for position, score in index.search(vector, limit=limit):
                        chunk = vectors_map[position][1]
                        hits.append(
                            {
                                **chunk,
                                "score": score,
                                "mode": "vector",
                            }
                        )
                    continue
                except Exception:
                    # 查询时嵌入失败：本次调用退回词法
                    pass
            documents = [chunk["text"] for chunk in chunks]
            for position, score in search_lexical(
                query, documents, limit=limit
            ):
                hits.append({**chunks[position], "score": score, "mode": "lexical"})

        hits.sort(key=lambda item: item["score"], reverse=True)
        if min_score is not None:
            hits = [hit for hit in hits if hit["score"] >= min_score]
        return hits[:limit]

    def context_for(
        self,
        query: str,
        limit: int = 5,
        max_chars: int = 3000,
        min_score: float = 0.25,
    ) -> str:
        hits = self.search(
            query,
            limit=limit,
            min_score=min_score,
        )
        if not hits:
            return ""
        lines: list[str] = []
        used = 0
        for hit in hits:
            line = (
                f"- [{hit['source_name']}/{hit['path']}#{hit['index']}] "
                f"(score {hit['score']:.2f})\n  {hit['text']}"
            )
            if used + len(line) > max_chars:
                break
            lines.append(line)
            used += len(line)
        return "\n".join(lines)


__all__ = ["RAGManager", "EmbeddingProvider", "default_rag_path"]
