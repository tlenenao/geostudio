# SPDX-License-Identifier: Apache-2.0
"""Garde d'egress SSRF (SP-12d §3). Le worker émet des requêtes HTTP vers une
URL fournie par un admin ; cette garde bloque les cibles réseau internes
(loopback / privé / link-local / réservé / multicast / unspecified), avec une
allowlist optionnelle par env. Point d'enforcement : le transport du client
HTTP par défaut de tous les connecteurs et de la récupération copie.

Résiduel documenté (§3, §8) : DNS-rebinding TOCTOU — la garde valide l'IP
résolue AVANT la requête, httpx re-résout au connect. Le pinning-IP est différé
(fragile avec TLS/vhosts). Les cibles SSRF à forte valeur (métadonnées cloud,
localhost) sont des IP-littérales ou résolvent stablement : couvertes en v0."""

import ipaddress
import logging
import os
import socket
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT_SECONDS = 10.0
_ALLOWLIST_ENV = "CORE_HARVEST_EGRESS_ALLOWLIST"
_MAX_RESPONSE_BYTES_ENV = "CORE_HARVEST_MAX_RESPONSE_BYTES"
_DEFAULT_MAX_RESPONSE_BYTES = 10 * 1024 * 1024  # 10 Mio


class EgressBlockedError(Exception):
    """Cible réseau interdite (plage interne ou hors allowlist)."""


class ResponseTooLargeError(Exception):
    """Réponse distante dépassant CORE_HARVEST_MAX_RESPONSE_BYTES (GAP-59,
    SP-50) — non capturée par les connecteurs, remonte jusqu'à
    harvest_source qui la traite comme n'importe quelle autre exception de
    connector.fetch() (source.last_status devient "error")."""


def _max_response_bytes() -> int:
    raw = os.environ.get(_MAX_RESPONSE_BYTES_ENV, "")
    return int(raw) if raw.strip() else _DEFAULT_MAX_RESPONSE_BYTES


def _allowlist() -> set[str]:
    raw = os.environ.get(_ALLOWLIST_ENV, "")
    return {h.strip() for h in raw.split(",") if h.strip()}


def _is_internal(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return (
        ip.is_loopback
        or ip.is_private
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


def assert_egress_allowed(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme.lower() not in {"http", "https"}:
        raise EgressBlockedError(f"schéma d'egress interdit : {parsed.scheme!r}")
    host = parsed.hostname
    if not host:
        raise EgressBlockedError(f"hôte d'egress absent dans l'URL : {url!r}")

    try:
        addresses = [ipaddress.ip_address(host)]
    except ValueError:
        try:
            infos = socket.getaddrinfo(host, None)
        except socket.gaierror as exc:
            raise EgressBlockedError(f"hôte non résoluble : {host!r}") from exc
        addresses = [ipaddress.ip_address(info[4][0]) for info in infos]

    for ip in addresses:
        if _is_internal(ip):
            raise EgressBlockedError(f"cible réseau interne bloquée : {host!r} → {ip}")

    allowlist = _allowlist()
    if allowlist and host not in allowlist:
        raise EgressBlockedError(f"hôte hors allowlist d'egress : {host!r}")


class _GuardedTransport(httpx.BaseTransport):
    def __init__(self, inner: httpx.BaseTransport):
        self._inner = inner

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        assert_egress_allowed(str(request.url))
        response = self._inner.handle_request(request)
        cap = _max_response_bytes()
        chunks: list[bytes] = []
        total = 0
        try:
            for chunk in response.stream:
                total += len(chunk)
                if total > cap:
                    raise ResponseTooLargeError(
                        f"réponse distante > {cap} octets pour {request.url}"
                    )
                chunks.append(chunk)
        finally:
            response.close()
        return httpx.Response(
            status_code=response.status_code,
            headers=response.headers,
            content=b"".join(chunks),
            request=request,
        )


def build_guarded_client(timeout: float = _DEFAULT_TIMEOUT_SECONDS) -> httpx.Client:
    return httpx.Client(transport=_GuardedTransport(httpx.HTTPTransport()), timeout=timeout)


def guarded_get(url: str, *, timeout: float = _DEFAULT_TIMEOUT_SECONDS) -> httpx.Response:
    with build_guarded_client(timeout) as client:
        response = client.get(url)
        response.raise_for_status()
        return response
