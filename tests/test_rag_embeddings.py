from __future__ import annotations

from geass.rag.embeddings import EmbeddingProvider, provider_from_config


class FakeEmbeddingClient:
    def __init__(self, vectors=None, fail=False):
        self.vectors = vectors or [[0.1, 0.2, 0.3]]
        self.fail = fail
        self.embeddings = self

    def create(self, model=None, input=None):
        if self.fail:
            raise RuntimeError("embedding unavailable")

        class Item:
            pass

        data = []
        for _ in input:
            item = Item()
            item.embedding = list(self.vectors[0])
            data.append(item)

        class Response:
            pass

        response = Response()
        response.data = data
        return response


def test_provider_disabled_without_base_url():
    provider = EmbeddingProvider(model="text-embedding-3-small")
    assert provider.enabled is False
    assert provider.probe() == (False, 0)


def test_provider_probe_and_embed(monkeypatch):
    provider = EmbeddingProvider(
        base_url="https://example.com/v1",
        model="fake-embed",
    )
    monkeypatch.setattr(provider, "_ensure_client", lambda: FakeEmbeddingClient())

    assert provider.probe() == (True, 3)
    vectors = provider.embed_texts(["a", "b"])
    assert vectors == [[0.1, 0.2, 0.3], [0.1, 0.2, 0.3]]


def test_provider_probe_failure_returns_false(monkeypatch):
    provider = EmbeddingProvider(
        base_url="https://example.com/v1",
        model="fake-embed",
    )
    monkeypatch.setattr(provider, "_ensure_client", lambda: FakeEmbeddingClient(fail=True))

    assert provider.probe() == (False, 0)


def test_provider_from_config():
    class Agent:
        embedding_enabled = True
        embedding_base_url = "https://example.com/v1"
        embedding_model = "fake"

    class Config:
        api_key = "sk-test"
        agent = Agent()

    provider = provider_from_config(Config())
    assert provider is not None
    assert provider.base_url == "https://example.com/v1"
