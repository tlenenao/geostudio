# SPDX-License-Identifier: Apache-2.0
"""Épinglage de la connexion sur l'adresse validée par la garde d'egress
(REV-273d, anti-TOCTOU DNS). Module sans dépendance applicative : partagé
par les copies de la garde (pipelines/alerts/harvest/copilot/search) que
le contrat de couches empêche de s'importer entre elles.

`resolve(host)` doit appliquer la garde d'egress et retourner l'IP validée
(ou None pour ne rien imposer, ex. garde neutralisée en test) ; une
adresse interne lève l'exception de la garde. Le nom d'hôte d'origine
reste utilisé pour `Host:` et pour le SNI/la vérification du certificat."""

from collections.abc import Callable
from typing import Any

import httpx
from requests.adapters import HTTPAdapter
from urllib3.connection import HTTPConnection, HTTPSConnection
from urllib3.connectionpool import HTTPConnectionPool, HTTPSConnectionPool

Resolve = Callable[[str], str | None]


def pinned_adapter(base: type[HTTPAdapter], resolve: Resolve) -> type[HTTPAdapter]:
    """Sous-classe de `base` dont les connexions TCP visent `resolve(host)`.

    urllib3 2.x : `_new_conn()` connecte sur `_dns_host`, et `host` (donc le
    server_hostname TLS, lu juste après dans `connect()`) en dérive ; on ne
    substitue `_dns_host` que le temps de `_new_conn()`. `Host:` est posé
    par requests depuis l'URL, indépendamment. Chaque redirection repasse
    par `send()` puis, pour un nouvel hôte, par `_new_conn()` : re-validée
    et épinglée. Une connexion keep-alive réutilisée reste sur l'IP validée
    à sa création.
    ponytail: première adresse validée uniquement (pas de repli sur les
    suivantes) ; ProxyManager (variables HTTP(S)_PROXY) non épinglé, la
    garde de send() y reste la seule protection."""

    def _pin(conn_cls: type[HTTPConnection]) -> type[HTTPConnection]:
        class Pinned(conn_cls):  # type: ignore[misc, valid-type]
            def _new_conn(self) -> Any:
                real = self._dns_host  # type: ignore[has-type]
                ip = resolve(real)
                if ip:
                    self._dns_host = ip
                try:
                    return super()._new_conn()
                finally:
                    self._dns_host = real

        return Pinned

    class _HTTPPool(HTTPConnectionPool):
        ConnectionCls = _pin(HTTPConnection)

    class _HTTPSPool(HTTPSConnectionPool):
        ConnectionCls = _pin(HTTPSConnection)  # type: ignore[assignment]

    class PinnedAdapter(base):  # type: ignore[misc, valid-type]
        def init_poolmanager(self, *args: Any, **kwargs: Any) -> None:
            super().init_poolmanager(*args, **kwargs)
            self.poolmanager.pool_classes_by_scheme = {"http": _HTTPPool, "https": _HTTPSPool}

    return PinnedAdapter


def pin_httpx_request(request: httpx.Request, ip: str | None) -> None:
    """Redirige `request` vers `ip` en gardant `Host:` (déjà posé à la
    construction) et le SNI/la vérification TLS (extension httpcore
    `sni_hostname`)."""
    if not ip:
        return
    request.extensions["sni_hostname"] = request.url.host
    request.url = request.url.copy_with(host=ip)
