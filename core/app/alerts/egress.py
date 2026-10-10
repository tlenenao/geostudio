# SPDX-License-Identifier: Apache-2.0
"""SSRF egress guard for AlertRule webhook delivery (design SP-16b §5) —
deliberate duplication of app.pipelines.egress/app.harvest.egress: the
webhook URL is user-supplied per rule (unlike the SMTP secret, which is
admin-configured, cf. Global Constraints), same threat model as the two
existing guards. Own CORE_ALERTS_EGRESS_ALLOWLIST env var, distinct from
CORE_PIPELINES_EGRESS_ALLOWLIST/CORE_HARVEST_EGRESS_ALLOWLIST — same
duplication rationale as the guard itself."""

import ipaddress
import logging
import os
import socket
from urllib.parse import urlparse

import requests

from app.net_pin import ValidatedIp, pinned_adapter

logger = logging.getLogger(__name__)

_ALLOWLIST_ENV = "CORE_ALERTS_EGRESS_ALLOWLIST"


class EgressBlockedError(Exception):
    """Cible réseau interdite (plage interne ou hors allowlist)."""


def _allowlist() -> set[str]:
    raw = os.environ.get(_ALLOWLIST_ENV, "")
    return {h.strip() for h in raw.split(",") if h.strip()}


def _is_internal(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    # tout ce qui n'est pas globalement routable (CGNAT 100.64/10, TEST-NET, 6to4…)
    # fec0::/10 (site-local déprécié) : is_global le laisse passer (j06-003)
    return not ip.is_global or ip.is_multicast or getattr(ip, "is_site_local", False)


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
            raise EgressBlockedError(f"cible réseau interne bloquée : {host!r}")

    allowlist = _allowlist()
    if allowlist and host not in allowlist:
        raise EgressBlockedError(f"hôte hors allowlist d'egress : {host!r}")
    return ValidatedIp(str(addresses[0]), [str(a) for a in addresses])  # REV-273d


def _pin_ip(host: str) -> str:
    # REV-273d : la connexion vise l'IP que la garde vient de valider (anti
    # DNS-rebinding entre contrôle et connexion). Lookup du nom global à
    # l'appel : reste neutralisable par les fixtures de tests
    # (`assert_egress_allowed` remplacé par un lambda → None → pas d'épinglage).
    return assert_egress_allowed(f"http://[{host}]" if ":" in host else f"http://{host}")


class _GuardedHTTPAdapter(pinned_adapter(requests.adapters.HTTPAdapter, _pin_ip)):  # type: ignore[misc]
    def send(self, request, **kwargs):
        assert_egress_allowed(request.url)
        return super().send(request, **kwargs)


def build_guarded_session() -> requests.Session:
    session = requests.Session()
    adapter = _GuardedHTTPAdapter()
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session
