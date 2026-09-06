# SPDX-License-Identifier: Apache-2.0
import socket

import httpx
import pytest

from app.harvest.egress import (
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
    monkeypatch.setenv("CORE_HARVEST_EGRESS_ALLOWLIST", "other.example.com")
    with pytest.raises(EgressBlockedError):
        assert_egress_allowed("https://public.example.com/x")
    monkeypatch.setenv("CORE_HARVEST_EGRESS_ALLOWLIST", "public.example.com,other.example.com")
    assert_egress_allowed("https://public.example.com/x")


def test_guarded_client_transport_blocks_before_connection():
    # 127.0.0.1:9 (discard) : la garde doit lever AVANT toute tentative de
    # connexion réseau — donc EgressBlockedError, jamais un ConnectError.
    client = build_guarded_client(timeout=1.0)
    with client:
        with pytest.raises(EgressBlockedError):
            client.get("http://127.0.0.1:9/x")


def test_guarded_transport_rejects_oversized_response(monkeypatch):
    from app.harvest.egress import ResponseTooLargeError, _GuardedTransport

    monkeypatch.setenv("CORE_HARVEST_MAX_RESPONSE_BYTES", "10")

    def handler(request):
        return httpx.Response(200, content=b"x" * 1000)

    inner = httpx.MockTransport(handler)
    # Contourne assert_egress_allowed (bloquerait un hôte de test interne) :
    # construire le client directement avec _GuardedTransport(inner), sans
    # passer par build_guarded_client() qui compose HTTPTransport() en dur.
    monkeypatch.setattr("app.harvest.egress.assert_egress_allowed", lambda url: None)
    client = httpx.Client(transport=_GuardedTransport(inner))
    with pytest.raises(ResponseTooLargeError):
        client.get("http://test/")


def test_guarded_transport_allows_response_within_limit(monkeypatch):
    from app.harvest.egress import _GuardedTransport

    monkeypatch.setenv("CORE_HARVEST_MAX_RESPONSE_BYTES", "10000")
    monkeypatch.setattr("app.harvest.egress.assert_egress_allowed", lambda url: None)

    def handler(request):
        return httpx.Response(200, content=b"ok", headers={"content-type": "application/json"})

    client = httpx.Client(transport=_GuardedTransport(httpx.MockTransport(handler)))
    resp = client.get("http://test/")
    assert resp.status_code == 200
    assert resp.content == b"ok"
