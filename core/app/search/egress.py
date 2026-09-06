# SPDX-License-Identifier: Apache-2.0
"""Garde d'egress SSRF sur l'appel d'embedding sortant (REV-042).

`OpenAICompatibleProvider.embed` (`app.search.providers`) postait directement
via `httpx.post()` au niveau module, sans passer par aucune garde d'egress
SSRF — la seule des 4 surfaces sortantes du dépôt à en être dépourvue
(moissonnage `app.harvest.egress`, connecteurs pipeline `app.pipelines.egress`,
egress LLM du copilote `app.copilot.egress`, en ont chacune une).

Ce module duplique la garde plutôt que d'importer `app.harvest.egress`
(pattern source, le plus complet) : chaque domaine a sa propre variable
d'environnement d'allowlist — `CORE_EMBEDDING_EGRESS_ALLOWLIST` ici, distincte
de `CORE_HARVEST_EGRESS_ALLOWLIST`/`CORE_PIPELINES_EGRESS_ALLOWLIST`/
`CORE_LLM_EGRESS_ALLOWLIST`. Même raison que `app.copilot.egress` (cf. sa
docstring) : un opérateur qui autoriserait un hôte de moissonnage ou un
connecteur pipeline ne doit pas de facto autoriser le fournisseur d'embedding
à y poster (ou réciproquement) — ce sont des surfaces à des périmètres de
confiance différents (réglage opérateur unique pour l'embedding, contre
sources créées par n'importe quel utilisateur privilégié pour le
moissonnage/les pipelines).

Différence avec `app.copilot.egress` : `OpenAICompatibleProvider.embed` est
**synchrone** (pas de `httpx.AsyncClient` — contrairement au provider LLM du
copilote, dont `chat` est async par contrat). Le patron à suivre est donc la
version synchrone (`app.harvest.egress`/`app.pipelines.egress`'s httpx
sibling), pas la version async. La garde enveloppe un `httpx.BaseTransport`
(synchrone), reconstruite une seule fois par instance de provider (pas par
appel) : `OpenAICompatibleProvider.__init__` construit son client gardé et le
réutilise sur chaque `embed()`.

Résiduel documenté (identique à `app.harvest.egress`) : DNS-rebinding TOCTOU —
la garde valide l'IP résolue AVANT la requête, httpx re-résout au connect.
`CORE_EMBEDDING_API_URL` est un réglage opérateur (pas une entrée
utilisateur), donc la surface d'attaque réelle est plus étroite que pour le
moissonnage — même compromis que documenté par `app.copilot.egress`."""

import ipaddress
import logging
import os
import socket
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT_SECONDS = 10.0
_ALLOWLIST_ENV = "CORE_EMBEDDING_EGRESS_ALLOWLIST"


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


class _GuardedTransport(httpx.BaseTransport):
    def __init__(self, inner: httpx.BaseTransport):
        self._inner = inner

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        assert_egress_allowed(str(request.url))
        return self._inner.handle_request(request)


def build_guarded_client(timeout: float = _DEFAULT_TIMEOUT_SECONDS) -> httpx.Client:
    return httpx.Client(transport=_GuardedTransport(httpx.HTTPTransport()), timeout=timeout)
