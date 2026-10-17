# SPDX-License-Identifier: Apache-2.0
"""Garde d'egress SSRF du géocodage (REV-102). Contrôle commun
(app.egress_guard, AUD-124) ; allowlist propre au domaine :
CORE_GEOCODING_EGRESS_ALLOWLIST, défaut « data.geopf.fr » quand la variable
est absente ; vide = seules les plages internes sont bloquées. Synchrone,
connexion sur l'IP validée (app.net_pin, REV-273d), jamais de suivi de
redirection (l'ancien hôte api-adresse.data.gouv.fr redirige)."""

import httpx

from app.egress_guard import check_url
from app.net_pin import ValidatedIp, send_pinned

_DEFAULT_TIMEOUT_SECONDS = 10.0
_ALLOWLIST_ENV = "CORE_GEOCODING_EGRESS_ALLOWLIST"
_DEFAULT_ALLOWLIST = "data.geopf.fr"


class EgressBlockedError(Exception):
    """Cible réseau interdite (plage interne ou hors allowlist)."""


def assert_egress_allowed(url: str) -> ValidatedIp:
    # AUD-124 : logique commune dans app.egress_guard ; seule l'allowlist est propre au domaine.
    return check_url(
        url,
        allowlist_env=_ALLOWLIST_ENV,
        default_allowlist=_DEFAULT_ALLOWLIST,
        error=EgressBlockedError,
    )


class _GuardedTransport(httpx.BaseTransport):
    def __init__(self, inner: httpx.BaseTransport):
        self._inner = inner

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        return send_pinned(
            self._inner.handle_request, request, assert_egress_allowed(str(request.url))
        )

    def close(self) -> None:
        self._inner.close()


def build_guarded_client(timeout: float = _DEFAULT_TIMEOUT_SECONDS) -> httpx.Client:
    return httpx.Client(
        transport=_GuardedTransport(httpx.HTTPTransport()),
        timeout=timeout,
        follow_redirects=False,
    )
