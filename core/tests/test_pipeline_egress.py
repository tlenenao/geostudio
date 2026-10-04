# SPDX-License-Identifier: Apache-2.0
import asyncio
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import aiohttp
import pytest
import requests
from botocore.exceptions import HTTPClientError

from app.pipelines.egress import (
    EgressBlockedError,
    PinnedAioResolver,
    assert_dsn_egress_allowed,
    assert_egress_allowed,
    build_guarded_session,
    dsn_pin_connect_args,
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
    monkeypatch.setenv("CORE_PIPELINES_EGRESS_ALLOWLIST", "other.example.com")
    with pytest.raises(EgressBlockedError):
        assert_egress_allowed("https://public.example.com/x")
    monkeypatch.setenv("CORE_PIPELINES_EGRESS_ALLOWLIST", "public.example.com,other.example.com")
    assert_egress_allowed("https://public.example.com/x")


def test_guarded_session_blocks_before_connection():
    # 127.0.0.1:9 (discard) : la garde doit lever AVANT toute tentative de
    # connexion réseau — donc EgressBlockedError, jamais un ConnectionError.
    session = build_guarded_session()
    with pytest.raises(EgressBlockedError):
        session.get("http://127.0.0.1:9/x", timeout=1.0)


def test_guarded_session_is_a_real_requests_session():
    session = build_guarded_session()
    assert isinstance(session, requests.Session)


@pytest.mark.parametrize("url", ["http://100.64.0.1/x", "http://198.51.100.7/x"])
def test_non_global_addresses_blocked(url):
    # CGNAT et TEST-NET : ni privées ni réservées au sens historique, mais non globales.
    with pytest.raises(EgressBlockedError):
        assert_egress_allowed(url)


@pytest.mark.parametrize(
    "dsn",
    [
        "postgresql://u:p@127.0.0.1/db",
        "postgresql://u:p@db.example/db?host=10.0.0.1",
        "postgresql://u:p@db.example/db?hostaddr=192.168.0.9,8.8.8.8",
        "mssql+pymssql://u:p@[::1]:1433/db",
        # hôte passé par un paramètre de pilote plutôt que par l'URL
        "mssql+pymssql://u:p@/db?server=127.0.0.1",
        "oracle+oracledb://u:p@/?dsn=127.0.0.1:1521/x",
        "mssql+pyodbc://u:p@/db?odbc_connect=SERVER%3D127.0.0.1",
    ],
)
def test_dsn_with_internal_host_blocked(dsn, monkeypatch):
    from app.pipelines.egress import assert_dsn_egress_allowed

    monkeypatch.setattr(
        socket, "getaddrinfo", lambda *a, **k: [(2, 1, 6, "", ("93.184.216.34", 0))]
    )
    with pytest.raises(EgressBlockedError):
        assert_dsn_egress_allowed(dsn)


def test_guarded_session_refuses_dns_rebinding_between_check_and_connect(monkeypatch):
    """Double résolveur : le contrôle de send() voit une IP publique, la
    résolution faite au moment de connecter voit 127.0.0.1 → refus."""
    answers = iter(["93.184.216.34", "127.0.0.1"])

    def fake_getaddrinfo(host, *args, **kwargs):
        ip = next(answers, "127.0.0.1")
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 0))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    session = build_guarded_session()
    with pytest.raises(EgressBlockedError):
        session.get("http://rebind.example.com:9/x", timeout=1.0)


def _seq_getaddrinfo(*ips):
    it = iter(ips)

    def fake(host, *args, **kwargs):
        ip = next(it, ips[-1])
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 0))]

    return fake


def test_dsn_pin_sets_hostaddr_to_the_validated_ip(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", _seq_getaddrinfo("93.184.216.34"))
    assert dsn_pin_connect_args("postgresql://u:p@db.example.com:5432/d") == {
        "hostaddr": "93.184.216.34"
    }


def test_dsn_pin_refuses_rebinding_to_loopback(monkeypatch):
    # 1re résolution (assert_dsn_egress_allowed) publique, 2e (épinglage) = 127.0.0.1
    monkeypatch.setattr(socket, "getaddrinfo", _seq_getaddrinfo("93.184.216.34", "127.0.0.1"))
    dsn = "postgresql://u:p@db.example.com/d"
    assert_dsn_egress_allowed(dsn)
    with pytest.raises(EgressBlockedError):
        dsn_pin_connect_args(dsn)


@pytest.mark.parametrize(
    "dsn",
    [
        "postgresql://u:p@93.184.216.34/d",  # littéral IP : rien à épingler
        "postgresql://u:p@/d?host=/var/run/postgresql",  # socket unix
        "postgresql://u:p@db.example.com/d?hostaddr=93.184.216.34",  # déjà épinglé
        "mssql+pymssql://u:p@db.example.com/d",  # pas d'équivalent hostaddr
    ],
)
def test_dsn_pin_is_empty_when_not_applicable(dsn, monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", _seq_getaddrinfo("93.184.216.34"))
    assert dsn_pin_connect_args(dsn) == {}


def test_pinned_aio_resolver_returns_the_validated_ip_and_keeps_hostname(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", _seq_getaddrinfo("93.184.216.34"))
    infos = asyncio.run(PinnedAioResolver().resolve("minio.example.com", 9000))
    assert infos[0]["host"] == "93.184.216.34"
    assert infos[0]["hostname"] == "minio.example.com"
    assert infos[0]["port"] == 9000 and infos[0]["family"] == socket.AF_INET


def test_pinned_aio_resolver_refuses_an_internal_answer(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", _seq_getaddrinfo("127.0.0.1"))
    with pytest.raises(EgressBlockedError):
        asyncio.run(PinnedAioResolver().resolve("minio.example.com", 9000))


@pytest.fixture
def local_http_server():
    seen: dict = {}

    class _Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            seen["host"] = self.headers["Host"]
            self.send_response(200)
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"ok")

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield server.server_address[1], seen
    server.shutdown()


def _aiohttp_get(url: str) -> str:
    async def _go() -> str:
        connector = aiohttp.TCPConnector(resolver=PinnedAioResolver())
        async with aiohttp.ClientSession(connector=connector) as s:
            async with s.get(url, timeout=aiohttp.ClientTimeout(total=5)) as r:
                return await r.text()

    return asyncio.run(_go())


def test_real_aiohttp_connector_connects_to_the_pinned_ip(monkeypatch, local_http_server):
    """Chemin réel aiohttp : la connexion TCP vise l'IP rendue par la garde
    (ici 127.0.0.1 simulée « validée »), le Host: garde le nom d'origine."""
    from app.pipelines import egress

    port, seen = local_http_server
    monkeypatch.setattr(egress, "assert_egress_allowed", lambda url: "127.0.0.1")
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: pytest.fail("DNS hors garde"))
    assert _aiohttp_get(f"http://s3.example.test:{port}/") == "ok"
    assert seen["host"] == f"s3.example.test:{port}"


def test_real_aiohttp_connector_refuses_rebinding_to_loopback(monkeypatch, local_http_server):
    port, seen = local_http_server
    monkeypatch.setattr(socket, "getaddrinfo", _seq_getaddrinfo("127.0.0.1"))
    with pytest.raises(EgressBlockedError):
        _aiohttp_get(f"http://s3.example.test:{port}/")
    assert seen == {}


def test_real_s3fs_client_goes_through_the_pinned_resolver(monkeypatch, local_http_server):
    """s3fs → aiobotocore AioConfig(connector_args) → aiohttp.TCPConnector :
    le résolveur passé dans config_kwargs est bien celui qui résout l'endpoint."""
    import s3fs

    port, seen = local_http_server
    monkeypatch.setattr(socket, "getaddrinfo", _seq_getaddrinfo("127.0.0.1"))
    fs = s3fs.S3FileSystem(
        key="k",
        secret="s",
        endpoint_url=f"http://minio.example.test:{port}",
        config_kwargs={"connector_args": {"resolver": PinnedAioResolver()}},
        skip_instance_cache=True,
    )
    # aiobotocore enveloppe l'exception du résolveur dans HTTPClientError.
    with pytest.raises(HTTPClientError, match="cible réseau interne bloquée"):
        fs.ls("bucket")
    assert seen == {}
