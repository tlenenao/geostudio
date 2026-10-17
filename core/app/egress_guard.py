# SPDX-License-Identifier: Apache-2.0
"""Garde d'egress SSRF unique (AUD-124). Module racine sans dépendance
applicative (hors liste `layers` du contrat import-linter, comme
`app.net_pin`/`app.sql_ident`) : chaque domaine n'y ajoute que sa variable
d'allowlist (périmètres de confiance distincts) et sa classe d'exception."""

import ipaddress
import os
import socket
from urllib.parse import urlparse

from app.net_pin import ValidatedIp

IP = ipaddress.IPv4Address | ipaddress.IPv6Address

_NAT64 = ipaddress.ip_network("64:ff9b::/96")


def embedded_ipv4(ip: IP) -> ipaddress.IPv4Address | None:
    """IPv4 transportée par une IPv6 (mappée, NAT64 bien connue, 6to4,
    IPv4-compatible dépréciée), sinon None."""
    if not isinstance(ip, ipaddress.IPv6Address):
        return None
    if ip.ipv4_mapped is not None:
        return ip.ipv4_mapped
    if ip in _NAT64:
        return ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF)
    if ip.sixtofour is not None:
        return ip.sixtofour
    if int(ip) >> 32 == 0 and int(ip) > 1:  # ::a.b.c.d (IPv4-compatible)
        return ipaddress.IPv4Address(int(ip))
    return None


def is_internal(ip: IP) -> bool:
    # tout ce qui n'est pas globalement routable (CGNAT 100.64/10, TEST-NET…) ;
    # fec0::/10 : is_global le laisse passer (j06-003) ; NAT64/::/96 : AUD-124.
    # Une IPv6 qui transporte une IPv4 est jugée sur cette IPv4 (déballée d'abord :
    # Python classe tout ::/8, donc 64:ff9b::/96, en is_reserved — un NAT64 public
    # derrière DNS64 doit rester joignable).
    v4 = embedded_ipv4(ip)
    if v4 is not None:
        return is_internal(v4)
    return (
        not ip.is_global or ip.is_multicast or ip.is_reserved or getattr(ip, "is_site_local", False)
    )


def allowlist(env: str, default: str = "") -> set[str]:
    raw = os.environ.get(env, default)
    return {h.strip() for h in raw.split(",") if h.strip()}


def check_url(
    url: str, *, allowlist_env: str, default_allowlist: str = "", error: type[Exception]
) -> ValidatedIp:
    parsed = urlparse(url)
    if parsed.scheme.lower() not in {"http", "https"}:
        raise error(f"schéma d'egress interdit : {parsed.scheme!r}")
    host = parsed.hostname
    if not host:
        raise error(f"hôte d'egress absent dans l'URL : {url!r}")
    try:
        addresses = [ipaddress.ip_address(host)]
    except ValueError:
        try:
            infos = socket.getaddrinfo(host, None)
        except socket.gaierror as exc:
            raise error(f"hôte non résoluble : {host!r}") from exc
        addresses = [ipaddress.ip_address(info[4][0]) for info in infos]
    if not addresses:
        raise error(f"hôte non résoluble : {host!r}")
    for ip in addresses:
        if is_internal(ip):
            raise error(f"cible réseau interne bloquée : {host!r}")
    allowed = allowlist(allowlist_env, default_allowlist)
    if allowed and host not in allowed:
        raise error(f"hôte hors allowlist d'egress : {host!r}")
    return ValidatedIp(str(addresses[0]), [str(a) for a in addresses])  # REV-273d
