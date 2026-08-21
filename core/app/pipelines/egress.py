# SPDX-License-Identifier: Apache-2.0
"""Garde d'egress SSRF pour reader.connector.rest (design SP-15f §5.1) —
duplication délibérée de app.harvest.egress : app.pipelines est positionné
SOUS app.harvest dans le contrat de couches import-linter
(core/pyproject.toml [[tool.importlinter.contracts]]), donc ne peut pas
l'importer. Point d'application différent de l'original : dlt.sources.rest_api
utilise `requests`, pas `httpx` — copier le transport httpx de
app.harvest.egress ne garderait rien en pratique."""

import ipaddress
import logging
import os
import socket
from urllib.parse import urlparse

import requests

logger = logging.getLogger(__name__)

# Variable dédiée, distincte de CORE_HARVEST_EGRESS_ALLOWLIST (app.harvest) :
# même logique de duplication que la garde elle-même, plutôt que de partager
# un état de configuration à travers la frontière de couches.
_ALLOWLIST_ENV = "CORE_PIPELINES_EGRESS_ALLOWLIST"


class EgressBlockedError(Exception):
    """Cible réseau interdite (plage interne ou hors allowlist)."""


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


class _GuardedHTTPAdapter(requests.adapters.HTTPAdapter):
    def send(self, request, **kwargs):
        assert_egress_allowed(request.url)
        return super().send(request, **kwargs)


def build_guarded_session() -> requests.Session:
    session = requests.Session()
    adapter = _GuardedHTTPAdapter()
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session
