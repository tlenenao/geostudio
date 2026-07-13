import pytest

from app.search.providers import EMBEDDING_DIM, FakeProvider, get_embedding_provider


def test_fake_provider_is_deterministic():
    provider = FakeProvider()
    v1 = provider.embed("incidents voirie")
    v2 = provider.embed("incidents voirie")
    assert v1 == v2
    assert len(v1) == EMBEDDING_DIM


def test_fake_provider_differs_for_different_text():
    provider = FakeProvider()
    assert provider.embed("a") != provider.embed("b")


def test_fake_provider_uses_explicit_vector_when_given():
    controlled = [1.0] * EMBEDDING_DIM
    provider = FakeProvider(vectors={"known text": controlled})
    assert provider.embed("known text") == controlled
    assert provider.embed("other text") != controlled  # repli sur le hash


def test_get_embedding_provider_defaults_to_fake(monkeypatch):
    monkeypatch.delenv("CORE_EMBEDDING_PROVIDER", raising=False)
    provider = get_embedding_provider()
    assert provider.__class__.__name__ == "FakeProvider"


def test_get_embedding_provider_openai_requires_config(monkeypatch):
    monkeypatch.setenv("CORE_EMBEDDING_PROVIDER", "openai")
    monkeypatch.delenv("CORE_EMBEDDING_API_URL", raising=False)
    with pytest.raises(KeyError):
        get_embedding_provider()


def test_get_embedding_provider_rejects_unknown_kind(monkeypatch):
    monkeypatch.setenv("CORE_EMBEDDING_PROVIDER", "nonsense")
    with pytest.raises(ValueError, match="nonsense"):
        get_embedding_provider()
