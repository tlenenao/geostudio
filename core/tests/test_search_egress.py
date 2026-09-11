# SPDX-License-Identifier: Apache-2.0
import socket

import httpx
import pytest

from app.search.egress import (
    EgressBlockedError,
    assert_egress_allowed,
    build_guarded_client,
)


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/x",
        "http://169.254.169.254/latest/meta-data/",
        "http://10.0.0.5/x",
        "http://192.168.1.1/x",
        "http://[::1]/x",
        "http://[fc00::1]/x",
        "http://0.0.0.0/x",
    ],
)
def test_assert_blocks_internal_ip_literals_without_dns(url):
    with pytest.raises(EgressBlockedError):
        assert_egress_allowed(url)


def test_assert_allows_public_ip_literal():
    assert_egress_allowed("https://93.184.216.34/x")


def test_assert_blocks_non_http_scheme():
    with pytest.raises(EgressBlockedError):
        assert_egress_allowed("file:///etc/passwd")
    with pytest.raises(EgressBlockedError):
        assert_egress_allowed("ftp://example.com/x")


def test_assert_blocks_hostname_resolving_to_internal(monkeypatch):
    def fake_getaddrinfo(host, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.1.2.3", 0))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    with pytest.raises(EgressBlockedError):
        assert_egress_allowed("https://evil.example.com/x")


def test_assert_allows_hostname_resolving_to_public(monkeypatch):
    def fake_getaddrinfo(host, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    assert_egress_allowed("https://public.example.com/x")


def test_allowlist_restricts_otherwise_allowed_public_host(monkeypatch):
    def fake_getaddrinfo(host, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    monkeypatch.setenv("CORE_EMBEDDING_EGRESS_ALLOWLIST", "other.example.com")
    with pytest.raises(EgressBlockedError):
        assert_egress_allowed("https://public.example.com/x")
    monkeypatch.setenv("CORE_EMBEDDING_EGRESS_ALLOWLIST", "public.example.com,other.example.com")
    assert_egress_allowed("https://public.example.com/x")


def test_guarded_client_transport_blocks_before_connection():
    # 127.0.0.1:9 (discard) : la garde doit lever AVANT toute tentative de
    # connexion réseau — donc EgressBlockedError, jamais un ConnectError.
    client = build_guarded_client(timeout=1.0)
    with client:
        with pytest.raises(EgressBlockedError):
            client.post("http://127.0.0.1:9/x", json={"input": "x"})


def test_openai_compatible_provider_embed_respects_egress_guard(monkeypatch):
    """Preuve que embed() passe réellement par le client gardé (pas un
    httpx.post() nu du module httpx) : une cible interne doit lever
    EgressBlockedError plutôt que tenter la connexion."""
    from app.search.providers import OpenAICompatibleProvider

    provider = OpenAICompatibleProvider(
        api_url="http://127.0.0.1:9/v1/embeddings",
        api_key="secret",
        model="text-embedding-3-small",
    )
    with pytest.raises(EgressBlockedError):
        provider.embed("incidents voirie")


def test_openai_compatible_provider_embed_blocked_by_allowlist(monkeypatch):
    """Cible publique mais hors allowlist dédiée à l'embedding : bloquée."""
    from app.search.providers import OpenAICompatibleProvider

    def fake_getaddrinfo(host, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    monkeypatch.setenv("CORE_EMBEDDING_EGRESS_ALLOWLIST", "other.example.com")

    provider = OpenAICompatibleProvider(
        api_url="https://public.example.com/v1/embeddings",
        api_key="secret",
        model="text-embedding-3-small",
    )
    with pytest.raises(EgressBlockedError):
        provider.embed("incidents voirie")


def test_openai_compatible_provider_embed_succeeds_when_allowed(monkeypatch):
    """Contrôle positif : quand l'egress est autorisé, embed() retourne bien
    le vecteur du corps de réponse (le client gardé ne casse pas le contrat
    fonctionnel existant)."""
    from app.search.providers import OpenAICompatibleProvider

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer secret"
        return httpx.Response(200, json={"data": [{"embedding": [0.1, 0.2, 0.3]}]})

    monkeypatch.setattr(
        "app.search.egress.assert_egress_allowed",
        lambda url: None,
    )

    provider = OpenAICompatibleProvider(
        api_url="https://public.example.com/v1/embeddings",
        api_key="secret",
        model="text-embedding-3-small",
    )
    # Remplace le transport interne du client déjà construit par l'instance,
    # pour intercepter la requête HTTP sans réseau réel.
    provider._client._transport = httpx.MockTransport(handler)
    assert provider.embed("incidents voirie") == [0.1, 0.2, 0.3]
