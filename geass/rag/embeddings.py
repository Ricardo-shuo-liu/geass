"""可插拔的嵌入 Provider：任意 OpenAI 兼容 embeddings 端点。"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

EMBED_BATCH_SIZE = 64


class EmbeddingProvider:
    """调用 OpenAI 兼容 ``/embeddings`` 接口；未配置端点时视为不可用。"""

    def __init__(
        self,
        api_key: str = "",
        base_url: str = "",
        model: str = "",
    ) -> None:
        self.api_key = api_key
        self.base_url = (base_url or "").strip().rstrip("/")
        self.model = (model or "").strip()
        self._client: Any = None

    @property
    def enabled(self) -> bool:
        return bool(self.base_url and self.model)

    def _ensure_client(self) -> Any:
        if self._client is None:
            from openai import OpenAI

            self._client = OpenAI(
                api_key=self.api_key or "not-needed",
                base_url=self.base_url,
            )
        return self._client

    def fingerprint(self, dim: int) -> str:
        return f"{self.model}@{dim}"

    def probe(self) -> tuple[bool, int]:
        """返回 ``(ok, dim)``；不可用或调用失败返回 ``(False, 0)``。"""
        if not self.enabled:
            return False, 0
        try:
            vectors = self.embed_texts(["probe"])
            if not vectors:
                return False, 0
            return True, len(vectors[0])
        except Exception as exc:
            logger.warning("嵌入端点探测失败，将使用本地词法检索：%s", exc)
            return False, 0

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        client = self._ensure_client()
        vectors: list[list[float]] = []
        for start in range(0, len(texts), EMBED_BATCH_SIZE):
            batch = texts[start : start + EMBED_BATCH_SIZE]
            response = client.embeddings.create(model=self.model, input=batch)
            vectors.extend([float(value) for value in item.embedding] for item in response.data)
        return vectors


def provider_from_config(config: Any) -> EmbeddingProvider | None:
    """从配置对象（含 agent 字段）构建 Provider；未启用返回 None。

    这是全仓库唯一保留 ``getattr`` 默认值的地方：调用方既可能传入完整的
    :class:`~geass.config.Config`，也可能直接传入
    :class:`~geass.config.AgentConfig`，因此有意做鸭子类型适配。
    """
    agent = getattr(config, "agent", config)
    if not getattr(agent, "embedding_enabled", True):
        return None
    base_url = str(getattr(agent, "embedding_base_url", "") or "").strip()
    model = str(getattr(agent, "embedding_model", "") or "").strip()
    if not base_url or not model:
        return None
    api_key = str(getattr(config, "api_key", "") or "")
    return EmbeddingProvider(
        api_key=api_key,
        base_url=base_url,
        model=model,
    )
