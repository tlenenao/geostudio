# SPDX-License-Identifier: Apache-2.0
"""Fournisseur d'embeddings enfichable (SP-7). Deux implémentations : un
provider HTTP compatible OpenAI/Voyage pour la production, et un provider
déterministe sans réseau pour dev/test/mock (CORE_EMBEDDING_PROVIDER=fake,
même convention que CORE_AUTH_MODE=mock). Le hash du FakeProvider n'a aucun
sens sémantique — il garantit seulement "même texte -> même vecteur", ce qui
suffit à exercer le mécanisme de recherche hybride en test. Les tests qui
veulent contrôler quels textes se ressemblent injectent une table
text -> vecteur explicite plutôt que de dépendre du hash."""

import hashlib
import os
import random
from typing import Protocol

import httpx

EMBEDDING_DIM = 1536


class EmbeddingProvider(Protocol):
    def embed(self, text: str) -> list[float]: ...


class FakeProvider:
    def __init__(self, vectors: dict[str, list[float]] | None = None):
        self._vectors = vectors or {}

    def embed(self, text: str) -> list[float]:
        if text in self._vectors:
            return self._vectors[text]
        seed = int(hashlib.sha256(text.encode("utf-8")).hexdigest(), 16) % (2**32)
        rng = random.Random(seed)
        return [rng.uniform(-1.0, 1.0) for _ in range(EMBEDDING_DIM)]


class OpenAICompatibleProvider:
    def __init__(self, *, api_url: str, api_key: str, model: str):
        self._api_url = api_url
        self._api_key = api_key
        self._model = model

    def embed(self, text: str) -> list[float]:
        response = httpx.post(
            self._api_url,
            headers={"Authorization": f"Bearer {self._api_key}"},
            json={"input": text, "model": self._model},
            timeout=10.0,
        )
        response.raise_for_status()
        return response.json()["data"][0]["embedding"]


def get_embedding_provider() -> EmbeddingProvider:
    kind = os.environ.get("CORE_EMBEDDING_PROVIDER", "fake")
    if kind == "fake":
        return FakeProvider()
    if kind == "openai":
        return OpenAICompatibleProvider(
            api_url=os.environ["CORE_EMBEDDING_API_URL"],
            api_key=os.environ["CORE_EMBEDDING_API_KEY"],
            model=os.environ.get("CORE_EMBEDDING_MODEL", "text-embedding-3-small"),
        )
    raise ValueError(f"unknown CORE_EMBEDDING_PROVIDER: {kind}")
