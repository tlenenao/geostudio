# SPDX-License-Identifier: Apache-2.0
"""REV-273d : épinglage DNS de la couche d'egress (5 copies de la garde)."""

import asyncio
import importlib
import socket

import httpx
import pytest

EGRESS_MODULES = [
    "app.pipelines.egress",
    "app.alerts.egress",
    "app.harvest.egress",
    "app.copilot.egress",
    "app.search.egress",
    "app.geocoding.egress",
]
PUBLIC = "93.184.216.34"


@pytest.fixture(autouse=True)
def _no_default_geocoding_allowlist(monkeypatch):
    # app.geocoding.egress a une allowlist par défaut (data.geopf.fr) ; ces tests
    # exercent la seule garde réseau sur des hôtes arbitraires.
    monkeypatch.setenv("CORE_GEOCODING_EGRESS_ALLOWLIST", "")


def _resolver(*answers):
    """getaddrinfo qui renvoie successivement `answers` (le dernier se répète)."""
    calls = {"n": 0}

    def fake(host, *args, **kwargs):
        ip = answers[min(calls["n"], len(answers) - 1)]
        calls["n"] += 1
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 0))]

    return fake, calls


@pytest.mark.parametrize("modname", EGRESS_MODULES)
def test_assert_returns_the_validated_address(monkeypatch, modname):
    mod = importlib.import_module(modname)
    fake, _ = _resolver(PUBLIC)
    monkeypatch.setattr(socket, "getaddrinfo", fake)
    assert mod.assert_egress_allowed("https://public.example.com/x") == PUBLIC
    assert mod.assert_egress_allowed("https://93.184.216.34:8443/x") == PUBLIC


@pytest.mark.parametrize("modname", EGRESS_MODULES)
def test_empty_resolution_is_refused(monkeypatch, modname):
    mod = importlib.import_module(modname)
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [])
    with pytest.raises(mod.EgressBlockedError):
        mod.assert_egress_allowed("https://empty.example.com/x")


@pytest.mark.parametrize("modname", EGRESS_MODULES)
def test_second_resolution_to_loopback_is_refused(monkeypatch, modname):
    """Double résolveur : 1re réponse publique (contrôle), 2e réponse 127.0.0.1
    (rebinding au moment de la connexion) → la 2e passe par la même garde."""
    mod = importlib.import_module(modname)
    fake, _ = _resolver(PUBLIC, "127.0.0.1")
    monkeypatch.setattr(socket, "getaddrinfo", fake)
    assert mod.assert_egress_allowed("https://rebind.example.com/x") == PUBLIC
    with pytest.raises(mod.EgressBlockedError):
        mod.assert_egress_allowed("https://rebind.example.com/x")


def _snapshot(request: httpx.Request) -> httpx.Request:
    # Copie à l'instant de l'envoi : send_pinned restaure ensuite `request.url`
    # (Location relatif, REV-273d), la requête d'origine ne montre plus l'IP.
    return httpx.Request(
        request.method, request.url, headers=request.headers, extensions=dict(request.extensions)
    )


class _Recorder(httpx.BaseTransport):
    def __init__(self):
        self.seen: list[httpx.Request] = []

    def handle_request(self, request):
        self.seen.append(_snapshot(request))
        return httpx.Response(200, content=b"ok", request=request)


class _AsyncRecorder(httpx.AsyncBaseTransport):
    def __init__(self):
        self.seen: list[httpx.Request] = []

    async def handle_async_request(self, request):
        self.seen.append(_snapshot(request))
        return httpx.Response(200, content=b"ok", request=request)


@pytest.mark.parametrize(
    "modname", ["app.harvest.egress", "app.search.egress", "app.geocoding.egress"]
)
def test_sync_httpx_transport_connects_to_validated_ip(monkeypatch, modname):
    mod = importlib.import_module(modname)
    fake, _ = _resolver(PUBLIC)
    monkeypatch.setattr(socket, "getaddrinfo", fake)
    inner = _Recorder()
    client = httpx.Client(transport=mod._GuardedTransport(inner))
    assert client.get("https://api.example.com:8443/v1/x").status_code == 200
    req = inner.seen[0]
    assert req.url.host == PUBLIC and req.url.port == 8443
    assert req.headers["host"] == "api.example.com:8443"
    assert req.extensions["sni_hostname"] == "api.example.com"


def test_copilot_async_transport_connects_to_validated_ip(monkeypatch):
    from app.copilot import egress as mod

    fake, _ = _resolver(PUBLIC)
    monkeypatch.setattr(socket, "getaddrinfo", fake)
    inner = _AsyncRecorder()

    async def go():
        async with httpx.AsyncClient(transport=mod._GuardedAsyncTransport(inner)) as client:
            return await client.get("https://llm.example.com/v1/chat")

    assert asyncio.run(go()).status_code == 200
    req = inner.seen[0]
    assert req.url.host == PUBLIC
    assert req.headers["host"] == "llm.example.com"
    assert req.extensions["sni_hostname"] == "llm.example.com"


def test_httpx_transport_neutralised_guard_does_not_pin(monkeypatch):
    """Garde remplacée (fixtures de tests existantes) → None → pas d'épinglage."""
    from app.harvest import egress as mod

    monkeypatch.setattr(mod, "assert_egress_allowed", lambda url: None)
    inner = _Recorder()
    httpx.Client(transport=mod._GuardedTransport(inner)).get("http://127.0.0.1:1234/x")
    assert inner.seen[0].url.host == "127.0.0.1"
    assert "sni_hostname" not in inner.seen[0].extensions


@pytest.mark.parametrize("modname", EGRESS_MODULES)
def test_getaddrinfo_triples_are_deduplicated(monkeypatch, modname):
    """getaddrinfo(host, None) renvoie STREAM/DGRAM/RAW par IP : `.addresses`
    ne doit contenir chaque IP qu'une fois (sinon 3 tentatives par IP morte)."""
    mod = importlib.import_module(modname)
    other = "93.184.216.35"

    def fake(host, *a, **k):
        return [
            (socket.AF_INET, t, 0, "", (ip, 0))
            for ip in (PUBLIC, other)
            for t in (socket.SOCK_STREAM, socket.SOCK_DGRAM, socket.SOCK_RAW)
        ]

    monkeypatch.setattr(socket, "getaddrinfo", fake)
    assert mod.assert_egress_allowed("https://dup.example.com/x").addresses == (PUBLIC, other)


def test_send_pinned_tries_each_ip_once(monkeypatch):
    from app.net_pin import ValidatedIp, send_pinned

    ip = ValidatedIp(PUBLIC, [PUBLIC, PUBLIC, PUBLIC, "93.184.216.35"])
    tried = []

    def send(req):
        tried.append(req.url.host)
        if len(tried) < 2:
            raise httpx.ConnectError("down")
        return httpx.Response(200)

    send_pinned(send, httpx.Request("GET", "https://api.example.com/x"), ip)
    assert tried == [PUBLIC, "93.184.216.35"]


@pytest.mark.parametrize("modname", EGRESS_MODULES)
def test_block_message_does_not_leak_resolved_ip(monkeypatch, modname):
    mod = importlib.import_module(modname)
    fake, _ = _resolver("10.1.2.3")
    monkeypatch.setattr(socket, "getaddrinfo", fake)
    with pytest.raises(mod.EgressBlockedError) as exc:
        mod.assert_egress_allowed("https://internal.example.com/x")
    assert "10.1.2.3" not in str(exc.value)
