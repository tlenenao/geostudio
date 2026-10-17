# SPDX-License-Identifier: Apache-2.0
"""Garde d'egress SSRF (SP-12d §3). Le worker émet des requêtes HTTP vers une
URL fournie par un admin ; cette garde bloque les cibles réseau internes
(loopback / privé / link-local / réservé / multicast / unspecified), avec une
allowlist optionnelle par env. Point d'enforcement : le transport du client
HTTP par défaut de tous les connecteurs et de la récupération copie.

DNS-rebinding TOCTOU (§3, §8) fermé par REV-273d : le transport connecte sur
l'IP validée par la garde (`app.net_pin.send_pinned`, Host/SNI/certificat
sur le nom d'origine), chaque redirection repasse par le transport."""

import logging
import os

import httpx

from app.egress_guard import check_url
from app.net_pin import ValidatedIp, send_pinned

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


def assert_egress_allowed(url: str) -> ValidatedIp:
    # AUD-124 : logique commune dans app.egress_guard ; seule l'allowlist est propre au domaine.
    return check_url(url, allowlist_env=_ALLOWLIST_ENV, error=EgressBlockedError)


class _GuardedTransport(httpx.BaseTransport):
    def __init__(self, inner: httpx.BaseTransport):
        self._inner = inner

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        response = send_pinned(
            self._inner.handle_request, request, assert_egress_allowed(str(request.url))
        )
        cap = _max_response_bytes()
        chunks: list[bytes] = []
        total = 0
        try:
            # REV-340 : octets DÉCODÉS (gzip/deflate) — le plafond sur le flux compressé
            # laissait passer une bombe de décompression.
            for chunk in response.iter_bytes():
                total += len(chunk)
                if total > cap:
                    raise ResponseTooLargeError(
                        f"réponse distante > {cap} octets pour {request.url}"
                    )
                chunks.append(chunk)
        finally:
            response.close()
        headers = httpx.Headers(response.headers)
        headers.pop("content-encoding", None)  # le corps est déjà décodé
        headers.pop("content-length", None)
        return httpx.Response(
            status_code=response.status_code,
            headers=headers,
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
