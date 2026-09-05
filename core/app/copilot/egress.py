# SPDX-License-Identifier: Apache-2.0
"""Garde d'egress SSRF sur l'appel LLM sortant du copilote (GAP-02, SP-45).

`app.copilot` est légalement au-dessus d'`app.harvest` dans le contrat de
couches (`uv run lint-imports` autoriserait un import direct de
`app.harvest.egress.assert_egress_allowed`), mais ce module duplique quand
même la garde plutôt que de l'importer : `app.harvest.egress` lit son
allowlist depuis `CORE_HARVEST_EGRESS_ALLOWLIST`, câblée en pratique sur les
sources de moissonnage créées par n'importe quel utilisateur privilégié.
Réutiliser cette même fonction coifferait silencieusement l'allowlist du
copilote (réglage opérateur, un seul hébergeur LLM) sur celle du moissonnage
(surface multi-utilisateurs) — un opérateur qui autoriserait un hôte de
moissonnage autoriserait de facto le LLM à y poster, et réciproquement. Même
patron que `app.alerts.egress`/`app.pipelines.egress` : chacun sa propre
variable d'environnement, pour la même raison qu'eux.

Différence technique avec les 3 gardes synchrones existantes : le provider
LLM utilise `httpx.AsyncClient` par contrat (`LLMProvider.chat` est async — un
appel bloquant gèlerait la boucle d'événements du process, qui tourne sans
`--workers`). La garde enveloppe donc un `httpx.AsyncBaseTransport`, pas un
`httpx.BaseTransport`. La fonction de validation elle-même
(`assert_egress_allowed`, résolution DNS incluse) reste synchrone comme dans
les trois autres gardes : c'est un appel rapide (un seul `socket.getaddrinfo`),
même compromis qu'ailleurs.

Résiduel documenté (identique à `app.harvest.egress`) : TOCTOU DNS-rebinding
— la garde valide l'IP résolue avant la requête, httpx re-résout au connect.
`CORE_LLM_API_URL` est un réglage opérateur (pas une entrée utilisateur), donc
la surface d'attaque réelle est plus étroite que pour le moissonnage."""

import ipaddress
import logging
import os
import socket
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT_SECONDS = 10.0
_ALLOWLIST_ENV = "CORE_LLM_EGRESS_ALLOWLIST"


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


class _GuardedAsyncTransport(httpx.AsyncBaseTransport):
    def __init__(self, inner: httpx.AsyncBaseTransport):
        self._inner = inner

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        assert_egress_allowed(str(request.url))
        return await self._inner.handle_async_request(request)


def build_guarded_async_client(timeout: float = _DEFAULT_TIMEOUT_SECONDS) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=_GuardedAsyncTransport(httpx.AsyncHTTPTransport()), timeout=timeout
    )
