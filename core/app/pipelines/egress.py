# SPDX-License-Identifier: Apache-2.0
"""Garde d'egress SSRF pour reader.connector.rest (design SP-15f §5.1) —
duplication délibérée de app.harvest.egress : app.pipelines est positionné
SOUS app.harvest dans le contrat de couches import-linter
(core/pyproject.toml [[tool.importlinter.contracts]]), donc ne peut pas
l'importer. Point d'application différent de l'original : dlt.sources.rest_api
utilise `requests`, pas `httpx` — copier le transport httpx de
app.harvest.egress ne garderait rien en pratique."""

import asyncio
import ipaddress
import logging
import os
import socket
from urllib.parse import urlparse

import requests
from aiohttp.abc import AbstractResolver, ResolveResult
from sqlalchemy.engine import make_url

from app.net_pin import ValidatedIp, candidate_ips, pinned_adapter

logger = logging.getLogger(__name__)

# Variable dédiée, distincte de CORE_HARVEST_EGRESS_ALLOWLIST (app.harvest) :
# même logique de duplication que la garde elle-même, plutôt que de partager
# un état de configuration à travers la frontière de couches.
_ALLOWLIST_ENV = "CORE_PIPELINES_EGRESS_ALLOWLIST"


def _connect_timeout_s() -> int:
    return int(os.environ.get("CORE_PIPELINES_CONNECT_TIMEOUT_S") or 10)


def _read_timeout_s() -> int:
    return int(os.environ.get("CORE_PIPELINES_QUERY_TIMEOUT_S") or 60)


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


def assert_dsn_egress_allowed(dsn: str) -> None:
    """Même garde pour l'hôte d'un DSN SQLAlchemy (P16.02) — hôte de l'URL
    et paramètres libpq `host`/`hostaddr` (peuvent être multiples)."""
    url = make_url(dsn)
    # Paramètres de pilote qui désignent un hôte hors de l'URL (mssql/oracle) :
    # non analysables de façon fiable (descripteur TNS, chaîne ODBC) → refusés.
    if {"server", "dsn", "odbc_connect", "hostname", "address"} & set(url.query):
        raise EgressBlockedError("DSN : hôte porté par un paramètre de pilote, refusé")
    if not url.get_backend_name().startswith("postgresql") and {
        "host",
        "hostaddr",
        "https_proxy",
        "https_proxy_port",
        "config_dir",
    } & set(url.query):
        # pymssql/oracledb préfèrent ces paramètres à l'hôte épinglé (rebinding)
        # ou passent par un proxy non vérifié.
        raise EgressBlockedError("DSN : hôte ou proxy porté par un paramètre de pilote, refusé")
    hosts = [url.host or ""]
    for key in ("host", "hostaddr"):
        val = url.query.get(key, ())
        hosts += [val] if isinstance(val, str) else list(val)
    for entry in hosts:
        for host in entry.split(","):
            if host and not host.startswith("/"):  # chemin = socket unix : pas du réseau
                assert_egress_allowed(f"http://[{host}]" if ":" in host else f"http://{host}")


def dsn_pin_connect_args(dsn: str) -> dict[str, str]:
    """REV-273d : épingle la connexion Postgres sur l'IP validée par la garde
    (paramètre libpq `hostaddr` ; `host` reste le nom → `verify-full` intact).
    `{}` quand il n'y a rien à épingler. mssql/oracle : voir `pin_dsn_host`."""
    url = make_url(dsn)
    host = url.host or ""
    if (
        not url.get_backend_name().startswith("postgresql")
        or not host
        or host.startswith("/")
        or "," in host
        or "host" in url.query
        or "hostaddr" in url.query
    ):
        return {}
    try:
        ipaddress.ip_address(host)
        return {}  # littéral : déjà validé par assert_dsn_egress_allowed
    except ValueError:
        pass
    ip = assert_egress_allowed(f"http://{host}")
    return {"hostaddr": ip} if ip else {}


def pin_dsn_host(dsn: str) -> str:
    """REV-273d : épingle l'hôte d'un DSN mssql/oracle sur l'IP validée par la
    garde (anti DNS-rebinding entre le contrôle et la connexion) en la
    substituant au nom dans l'URL. Ces pilotes n'ont pas de `hostaddr` : le
    nom est perdu pour la vérification TLS du certificat — l'opérateur qui
    l'exige indique l'hôte littéral. Oracle `protocol=tcps` n'est PAS épinglé
    (la vérification du DN du certificat porte sur l'hôte) : la garde amont
    reste appliquée, résidu TOCTOU (DNS-rebinding) assumé. ponytail: hôte unique résolu une fois
    (1re adresse validée) ; pas de repli multi-adresses pour ces pilotes."""
    url = make_url(dsn)
    host = url.host or ""
    backend = url.get_backend_name()
    if (
        not (backend.startswith("mssql") or backend.startswith("oracle"))
        or not host
        or host.startswith("/")
        or "," in host
        or str(url.query.get("protocol", "")).lower() == "tcps"
    ):
        return dsn
    try:
        ipaddress.ip_address(host)
        return dsn  # littéral : déjà validé par assert_dsn_egress_allowed
    except ValueError:
        pass
    ip = assert_egress_allowed(f"http://{host}")
    if not ip:
        return dsn  # garde neutralisée (fixtures de tests)
    # pymssql ajoute le port par `:` : un littéral IPv6 sans port explicite casse.
    port = (url.port or 1433) if backend.startswith("mssql") else url.port
    return url.set(host=str(ip), port=port).render_as_string(hide_password=False)


def _pin_ip(host: str) -> str:
    # REV-273d : la connexion vise l'IP que la garde vient de valider (anti
    # DNS-rebinding entre contrôle et connexion). Lookup du nom global à
    # l'appel : reste neutralisable par les fixtures de tests
    # (`assert_egress_allowed` remplacé par un lambda → None → pas d'épinglage).
    return assert_egress_allowed(f"http://[{host}]" if ":" in host else f"http://{host}")


class _GuardedHTTPAdapter(pinned_adapter(requests.adapters.HTTPAdapter, _pin_ip)):  # type: ignore[misc]
    def send(self, request, **kwargs):
        assert_egress_allowed(request.url)
        # requests n'a aucun délai par défaut (P16.03) : sans cela un serveur
        # lent bloque le worker indéfiniment. ponytail: délai par lecture,
        # pas un budget global ; un serveur qui goutte-à-goutte le contourne.
        if not kwargs.get("timeout"):
            kwargs["timeout"] = (_connect_timeout_s(), _read_timeout_s())
        return super().send(request, **kwargs)


def build_guarded_session() -> requests.Session:
    session = requests.Session()
    adapter = _GuardedHTTPAdapter()
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


class PinnedAioResolver(AbstractResolver):
    """Résolveur aiohttp (donc aiobotocore/s3fs, endpoint S3 compatible) qui
    n'accepte que les adresses validées par la garde d'egress au moment même de
    la connexion (REV-273d). `hostname` reste le nom d'origine : SNI et
    vérification de certificat inchangés. aiohttp (connector._resolve_host)
    n'appelle pas le résolveur pour un littéral IP : celui-ci est validé en
    amont par assert_egress_allowed(endpointUrl). Le cache DNS d'aiohttp
    (use_dns_cache, 10 s) ne réutilise que des réponses déjà validées."""

    async def resolve(
        self, host: str, port: int = 0, family: socket.AddressFamily = socket.AF_INET
    ) -> list[ResolveResult]:
        ip = await asyncio.to_thread(_pin_ip, host)  # getaddrinfo bloquant hors boucle
        # Toutes les adresses validées : aiohttp essaie la suivante si la 1re
        # est injoignable (double pile, REV-273d).
        return [
            {
                "hostname": host,
                "host": addr,
                "port": port,
                "family": socket.AF_INET6 if ":" in addr else socket.AF_INET,
                "proto": 0,
                "flags": socket.AI_NUMERICHOST,
            }
            for addr in candidate_ips(ip)
        ]

    async def close(self) -> None:
        return None
