# SPDX-License-Identifier: Apache-2.0
import asyncio
import datetime
import ssl
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer, ThreadingHTTPServer

import httpx
import pytest
import requests
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID
from requests.adapters import HTTPAdapter

from app.net_pin import (
    ValidatedIp,
    candidate_ips,
    pin_httpx_request,
    pinned_adapter,
    send_pinned,
    send_pinned_async,
)


class _Handler(BaseHTTPRequestHandler):
    seen: dict = {}

    def do_GET(self):
        _Handler.seen["host"] = self.headers["Host"]
        self.send_response(200)
        self.send_header("Content-Length", "2")
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *args):
        pass


def _serve(srv: HTTPServer) -> int:
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv.server_address[1]


def test_pinned_adapter_connects_to_resolved_ip_and_keeps_host_header():
    srv = HTTPServer(("127.0.0.1", 0), _Handler)
    port = _serve(srv)
    asked: list[str] = []

    def resolve(host: str) -> str:
        asked.append(host)
        return "127.0.0.1"

    try:
        session = requests.Session()
        session.mount("http://", pinned_adapter(HTTPAdapter, resolve)())
        # `.invalid` ne résout jamais : sans épinglage la requête échouerait.
        resp = session.get(f"http://pinned.invalid:{port}/", timeout=5)
    finally:
        srv.shutdown()
    assert resp.status_code == 200
    assert _Handler.seen["host"] == f"pinned.invalid:{port}"
    assert asked == ["pinned.invalid"]


def test_pinned_adapter_pins_redirect_targets_too():
    class Redirect(_Handler):
        def do_GET(self):
            if self.headers["Host"].startswith("first.invalid"):
                self.send_response(302)
                self.send_header("Location", f"http://second.invalid:{port}/")
                self.send_header("Content-Length", "0")
                self.end_headers()
            else:
                super().do_GET()

    srv = HTTPServer(("127.0.0.1", 0), Redirect)
    port = _serve(srv)
    asked: list[str] = []

    def resolve(host: str) -> str:
        asked.append(host)
        return "127.0.0.1"

    try:
        session = requests.Session()
        session.mount("http://", pinned_adapter(HTTPAdapter, resolve)())
        resp = session.get(f"http://first.invalid:{port}/", timeout=5)
    finally:
        srv.shutdown()
    assert resp.status_code == 200 and resp.history[0].status_code == 302
    assert asked == ["first.invalid", "second.invalid"]


def test_pinned_adapter_without_pin_falls_back_to_normal_dns():
    session = requests.Session()
    session.mount("http://", pinned_adapter(HTTPAdapter, lambda host: None)())
    with pytest.raises(requests.exceptions.ConnectionError):
        session.get("http://pinned.invalid:9/", timeout=2)


@pytest.fixture
def tls_server(tmp_path):
    """Serveur HTTPS 127.0.0.1 dont le certificat ne couvre QUE `pinned.test`
    (aucun SAN IP) : la vérification ne passe que si le SNI/le contrôle de nom
    utilisent le nom d'origine et non l'IP épinglée."""
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "pinned.test")])
    now = datetime.datetime.now(datetime.UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=1))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName("pinned.test")]), False)
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), True)
        .sign(key, hashes.SHA256())
    )
    cert_path, key_path = tmp_path / "cert.pem", tmp_path / "key.pem"
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    sni: list[str | None] = []

    class KeepAlive(_Handler):
        protocol_version = "HTTP/1.1"  # garde la connexion ouverte entre requêtes

    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2  # py/insecure-protocol (CodeQL)
    ctx.load_cert_chain(cert_path, key_path)
    ctx.sni_callback = lambda sock, server_name, _ctx: sni.append(server_name)
    srv = ThreadingHTTPServer(("127.0.0.1", 0), KeepAlive)
    srv.socket = ctx.wrap_socket(srv.socket, server_side=True)
    port = _serve(srv)
    yield port, str(cert_path), sni
    srv.shutdown()


def test_pinned_adapter_https_keeps_sni_and_verifies_cert_against_hostname(tls_server):
    port, ca, sni = tls_server
    session = requests.Session()
    session.mount("https://", pinned_adapter(HTTPAdapter, lambda host: "127.0.0.1")())
    resp = session.get(f"https://pinned.test:{port}/", timeout=5, verify=ca)
    assert resp.status_code == 200
    assert sni == ["pinned.test"]
    # La vérification reste active : un autre nom épinglé sur la même IP échoue.
    with pytest.raises(requests.exceptions.SSLError):
        session.get(f"https://other.test:{port}/", timeout=5, verify=ca)


def test_pin_httpx_request_rewrites_target_keeps_host_and_sni():
    req = httpx.Request("GET", "https://example.test:8443/x?y=1")
    pin_httpx_request(req, "93.184.216.34")
    assert req.url.host == "93.184.216.34" and req.url.port == 8443
    assert req.url.path == "/x" and req.url.query == b"y=1"
    assert req.headers["host"] == "example.test:8443"
    assert req.extensions["sni_hostname"] == "example.test"
    assert req.headers["connection"] == "close"


def test_pin_httpx_request_none_is_a_noop():
    req = httpx.Request("GET", "https://example.test/x")
    pin_httpx_request(req, None)
    assert req.url.host == "example.test" and "sni_hostname" not in req.extensions


def test_harvest_guarded_httpx_https_keeps_sni_and_verifies_cert_against_hostname(
    tls_server, monkeypatch
):
    """Bout en bout, vrai TLS httpcore : connexion sur l'IP épinglée, SNI et
    contrôle du certificat sur le nom d'origine."""
    from app.harvest import egress

    port, ca, sni = tls_server
    monkeypatch.setattr(egress, "assert_egress_allowed", lambda url: "127.0.0.1")

    def client() -> httpx.Client:
        return httpx.Client(
            transport=egress._GuardedTransport(
                httpx.HTTPTransport(verify=ssl.create_default_context(cafile=ca))
            )
        )

    with client() as c:
        assert c.get(f"https://pinned.test:{port}/").status_code == 200
    assert sni == ["pinned.test"]
    assert _Handler.seen["host"] == f"pinned.test:{port}"
    with client() as c, pytest.raises(httpx.ConnectError, match="CERTIFICATE_VERIFY_FAILED"):
        c.get(f"https://other.test:{port}/")
    # Même client, même IP, serveur keep-alive : la connexion vérifiée pour
    # pinned.test ne doit pas être réutilisée pour other.test.
    with client() as c:
        assert c.get(f"https://pinned.test:{port}/").status_code == 200
        with pytest.raises(httpx.ConnectError, match="CERTIFICATE_VERIFY_FAILED"):
            c.get(f"https://other.test:{port}/")


def test_validated_ip_is_a_str_carrying_every_validated_address():
    ip = ValidatedIp("1.2.3.4", ["1.2.3.4", "2001:db8::1"])
    assert ip == "1.2.3.4" and isinstance(ip, str)
    assert candidate_ips(ip) == ("1.2.3.4", "2001:db8::1")
    assert candidate_ips("5.6.7.8") == ("5.6.7.8",)
    assert candidate_ips(None) == ()


def test_pinned_adapter_falls_back_to_the_next_validated_address():
    srv = HTTPServer(("127.0.0.1", 0), _Handler)  # n'écoute QUE sur 127.0.0.1
    port = _serve(srv)

    def resolve(host: str) -> ValidatedIp:
        # 127.0.0.2 : connexion refusée immédiatement (rien n'y écoute) ; la
        # 2e adresse validée doit alors être essayée.
        return ValidatedIp("127.0.0.2", ["127.0.0.2", "127.0.0.1"])

    try:
        session = requests.Session()
        session.mount("http://", pinned_adapter(HTTPAdapter, resolve)())
        resp = session.get(f"http://pinned.invalid:{port}/", timeout=5)
    finally:
        srv.shutdown()
    assert resp.status_code == 200


def test_send_pinned_falls_back_and_restores_the_original_url():
    srv = HTTPServer(("127.0.0.1", 0), _Handler)
    port = _serve(srv)
    transport = httpx.HTTPTransport()
    request = httpx.Request("GET", f"http://pinned.invalid:{port}/")
    try:
        response = send_pinned(
            transport.handle_request,
            request,
            ValidatedIp("127.0.0.2", ["127.0.0.2", "127.0.0.1"]),
        )
        response.read()
    finally:
        srv.shutdown()
    assert response.status_code == 200
    assert _Handler.seen["host"] == f"pinned.invalid:{port}"
    # `Location` relatif sous follow_redirects=True : repart du nom d'origine.
    assert request.url.host == "pinned.invalid"


def test_send_pinned_raises_the_last_error_when_every_address_fails():
    transport = httpx.HTTPTransport()
    request = httpx.Request("GET", "http://pinned.invalid:9/")
    with pytest.raises(httpx.ConnectError):
        send_pinned(transport.handle_request, request, ValidatedIp("127.0.0.2", ["127.0.0.2"]))
    assert request.url.host == "pinned.invalid"


def test_send_pinned_without_pin_sends_as_is():
    seen = []

    def send(req):
        seen.append(str(req.url))
        return httpx.Response(200, request=req)

    request = httpx.Request("GET", "http://pinned.invalid:9/")
    assert send_pinned(send, request, None).status_code == 200
    assert seen == ["http://pinned.invalid:9/"]


def test_send_pinned_async_falls_back_too():
    srv = HTTPServer(("127.0.0.1", 0), _Handler)
    port = _serve(srv)
    transport = httpx.AsyncHTTPTransport()
    request = httpx.Request("GET", f"http://pinned.invalid:{port}/")

    async def run():
        response = await send_pinned_async(
            transport.handle_async_request,
            request,
            ValidatedIp("127.0.0.2", ["127.0.0.2", "127.0.0.1"]),
        )
        await response.aread()
        return response

    try:
        response = asyncio.run(run())
    finally:
        srv.shutdown()
    assert response.status_code == 200
    assert request.url.host == "pinned.invalid"
