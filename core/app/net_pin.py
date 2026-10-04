# SPDX-License-Identifier: Apache-2.0
"""Épinglage de la connexion sur l'adresse validée par la garde d'egress
(REV-273d, anti-TOCTOU DNS). Module sans dépendance applicative : partagé
par les copies de la garde (pipelines/alerts/harvest/copilot/search/geocoding) que
le contrat de couches empêche de s'importer entre elles.

`resolve(host)` doit appliquer la garde d'egress et retourner l'IP validée
(ou None pour ne rien imposer, ex. garde neutralisée en test) ; une
adresse interne lève l'exception de la garde. Le nom d'hôte d'origine
reste utilisé pour `Host:` et pour le SNI/la vérification du certificat."""

from collections.abc import Awaitable, Callable, Sequence
from typing import Any

import httpx
from requests.adapters import HTTPAdapter
from urllib3.connection import HTTPConnection, HTTPSConnection
from urllib3.connectionpool import HTTPConnectionPool, HTTPSConnectionPool
from urllib3.exceptions import ConnectTimeoutError, NewConnectionError

Resolve = Callable[[str], str | None]


class ValidatedIp(str):
    """Première adresse validée par la garde d'egress (valeur `str`, donc
    compatible avec tout appelant ou fixture qui traite le retour comme
    `str | None`) + TOUTES les adresses validées (REV-273d : seule la 1re
    était utilisée — AAAA d'abord en double pile — sans repli si elle est
    injoignable)."""

    addresses: tuple[str, ...]

    def __new__(cls, first: str, addresses: Sequence[str]) -> "ValidatedIp":
        obj = super().__new__(cls, first)
        obj.addresses = tuple(addresses)
        return obj


def candidate_ips(ip: str | None) -> tuple[str, ...]:
    """Adresses à essayer, dans l'ordre : `()` quand la garde est neutralisée
    (fixtures de tests) → aucun épinglage."""
    if not ip:
        return ()
    addresses: tuple[str, ...] | None = getattr(ip, "addresses", None)
    return addresses or (str(ip),)


def pinned_adapter(base: type[HTTPAdapter], resolve: Resolve) -> type[HTTPAdapter]:
    """Sous-classe de `base` dont les connexions TCP visent `resolve(host)`.

    urllib3 2.x : `_new_conn()` connecte sur `_dns_host`, et `host` (donc le
    server_hostname TLS, lu juste après dans `connect()`) en dérive ; on ne
    substitue `_dns_host` que le temps de `_new_conn()`. `Host:` est posé
    par requests depuis l'URL, indépendamment. Chaque redirection repasse
    par `send()` puis, pour un nouvel hôte, par `_new_conn()` : re-validée
    et épinglée. Une connexion keep-alive réutilisée reste sur l'IP validée
    à sa création.
    Chaque adresse validée est essayée tour à tour (repli sur un échec de
    connexion seulement).
    ponytail: ProxyManager (variables HTTP(S)_PROXY) non épinglé, la garde
    de send() y reste la seule protection."""

    def _pin(conn_cls: type[HTTPConnection]) -> type[HTTPConnection]:
        class Pinned(conn_cls):  # type: ignore[misc, valid-type]
            def _new_conn(self) -> Any:
                real = self._dns_host  # type: ignore[has-type]
                ips = candidate_ips(resolve(real))
                if not ips:
                    return super()._new_conn()
                last: Exception | None = None
                for ip in ips:
                    self._dns_host = ip
                    try:
                        return super()._new_conn()
                    except (NewConnectionError, ConnectTimeoutError) as exc:
                        last = exc
                    finally:
                        self._dns_host = real
                assert last is not None
                raise last

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
    `sni_hostname`).

    httpcore 1.0 regroupe ses connexions par origine (schéma, hôte, port) :
    une fois l'hôte réécrit en IP, deux noms résolus vers la même IP
    partageraient une connexion TLS dont le certificat n'a été vérifié que
    pour le premier (constaté sur un vrai serveur TLS keep-alive). En HTTPS,
    `Connection: close` interdit donc toute réutilisation : chaque requête
    ouvre sa connexion et vérifie le certificat pour son propre nom.
    ponytail: plus de keep-alive HTTPS sur les clients gardés (une poignée
    de main TLS par requête) ; pools par nom d'hôte si le coût se mesure."""
    if not ip:
        return
    request.extensions["sni_hostname"] = request.url.host
    if request.url.scheme == "https":
        request.headers["Connection"] = "close"
    request.url = request.url.copy_with(host=ip)


_CONNECT_ERRORS = (httpx.ConnectError, httpx.ConnectTimeout)


def send_pinned(
    send: Callable[[httpx.Request], httpx.Response], request: httpx.Request, ip: str | None
) -> httpx.Response:
    """Épingle `request` sur chaque adresse validée tour à tour (repli sur une
    erreur de CONNEXION seulement) puis restaure son URL d'origine : un client
    à `follow_redirects=True` résout un `Location` relatif contre
    `request.url` — laissé sur l'IP, il repartirait de l'IP au lieu du nom,
    hors garde (REV-273d, résidu « Location relatif »)."""
    ips = candidate_ips(ip)
    if not ips:
        return send(request)
    original = request.url
    last: Exception | None = None
    try:
        for candidate in ips:
            request.url = original
            pin_httpx_request(request, candidate)
            try:
                return send(request)
            except _CONNECT_ERRORS as exc:
                last = exc
        assert last is not None
        raise last
    finally:
        request.url = original


async def send_pinned_async(
    send: Callable[[httpx.Request], Awaitable[httpx.Response]],
    request: httpx.Request,
    ip: str | None,
) -> httpx.Response:
    """Pendant asynchrone de `send_pinned` (transport httpx asynchrone du copilote)."""
    ips = candidate_ips(ip)
    if not ips:
        return await send(request)
    original = request.url
    last: Exception | None = None
    try:
        for candidate in ips:
            request.url = original
            pin_httpx_request(request, candidate)
            try:
                return await send(request)
            except _CONNECT_ERRORS as exc:
                last = exc
        assert last is not None
        raise last
    finally:
        request.url = original
