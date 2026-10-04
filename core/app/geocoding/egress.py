# SPDX-License-Identifier: Apache-2.0
"""Garde d'egress SSRF du géocodage (REV-102). Copie délibérée de
app.search.egress (chaque domaine a sa propre allowlist, cf. sa docstring) :
CORE_GEOCODING_EGRESS_ALLOWLIST, défaut « data.geopf.fr » quand la variable
est absente ; vide = seules les plages internes sont bloquées. Synchrone,
connexion sur l'IP validée (app.net_pin, REV-273d), jamais de suivi de
redirection (l'ancien hôte api-adresse.data.gouv.fr redirige)."""

import ipaddress
import os
import socket
from urllib.parse import urlparse

import httpx

from app.net_pin import pin_httpx_request

_DEFAULT_TIMEOUT_SECONDS = 10.0
_ALLOWLIST_ENV = "CORE_GEOCODING_EGRESS_ALLOWLIST"
_DEFAULT_ALLOWLIST = "data.geopf.fr"


class EgressBlockedError(Exception):
    """Cible réseau interdite (plage interne ou hors allowlist)."""


def _allowlist() -> set[str]:
    raw = os.environ.get(_ALLOWLIST_ENV, _DEFAULT_ALLOWLIST)
    return {h.strip() for h in raw.split(",") if h.strip()}


def _is_internal(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    return not ip.is_global or ip.is_multicast


def assert_egress_allowed(url: str) -> str:
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
    if not addresses:
        raise EgressBlockedError(f"hôte non résoluble : {host!r}")
    for ip in addresses:
        if _is_internal(ip):
            raise EgressBlockedError(f"cible réseau interne bloquée : {host!r} → {ip}")
    allowlist = _allowlist()
    if allowlist and host not in allowlist:
        raise EgressBlockedError(f"hôte hors allowlist d'egress : {host!r}")
    return str(addresses[0])


class _GuardedTransport(httpx.BaseTransport):
    def __init__(self, inner: httpx.BaseTransport):
        self._inner = inner

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        pin_httpx_request(request, assert_egress_allowed(str(request.url)))
        return self._inner.handle_request(request)

    def close(self) -> None:
        self._inner.close()


def build_guarded_client(timeout: float = _DEFAULT_TIMEOUT_SECONDS) -> httpx.Client:
    return httpx.Client(
        transport=_GuardedTransport(httpx.HTTPTransport()),
        timeout=timeout,
        follow_redirects=False,
    )
