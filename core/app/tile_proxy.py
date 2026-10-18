# SPDX-License-Identifier: Apache-2.0
"""Appel TiTiler des proxys de tuiles (raster, terrain) : concurrence bornée + cache (AUD-056).

L'autorisation est toujours faite AVANT cet appel par la route ; le cache ne contient que le PNG
rendu depuis l'objet S3 (clé = URL TiTiler + paramètres, dont la clé S3), jamais lié à un
utilisateur. Une tuile écrasée sous la même clé S3 reste servie jusqu'à `_TTL_S` (60 s).
ponytail: cache en mémoire par processus, borné en octets ; cache partagé si plusieurs réplicas
doivent mutualiser."""

import os
import threading
import time
from collections import OrderedDict

import httpx

_TTL_S = 60.0
_LOCK = threading.Lock()
_CACHE: "OrderedDict[tuple, tuple[float, bytes]]" = OrderedDict()
_cache_bytes = 0
_sem: threading.BoundedSemaphore | None = None


class TileProxyBusyError(Exception):
    """Trop d'appels TiTiler simultanés : l'appelant répond 503."""


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "") or default)
    except ValueError:
        return default


def _semaphore() -> threading.BoundedSemaphore:
    global _sem
    if _sem is None:
        _sem = threading.BoundedSemaphore(max(1, _int_env("CORE_TILE_PROXY_CONCURRENCY", 16)))
    return _sem


def clear_cache() -> None:
    """Vide cache et sémaphore (tests, changement de configuration)."""
    global _cache_bytes, _sem
    with _LOCK:
        _CACHE.clear()
        _cache_bytes = 0
        _sem = None


def _store(key: tuple, content: bytes) -> None:
    global _cache_bytes
    budget = _int_env("CORE_TILE_PROXY_CACHE_BYTES", 64 * 1024 * 1024)
    if len(content) > budget:
        return
    with _LOCK:
        old = _CACHE.pop(key, None)
        if old:
            _cache_bytes -= len(old[1])
        _CACHE[key] = (time.monotonic(), content)
        _cache_bytes += len(content)
        while _cache_bytes > budget and _CACHE:
            _, (_, dropped) = _CACHE.popitem(last=False)
            _cache_bytes -= len(dropped)


def fetch_tile(url: str, params: dict[str, str], *, timeout: float = 10.0) -> tuple[int, bytes]:
    """(statut, corps). Lève httpx.HTTPError (panne) ou TileProxyBusyError (saturation)."""
    global _cache_bytes
    key = (url, tuple(sorted(params.items())))
    with _LOCK:
        hit = _CACHE.get(key)
        if hit and time.monotonic() - hit[0] < _TTL_S:
            _CACHE.move_to_end(key)
            return 200, hit[1]
        if hit:
            del _CACHE[key]
            _cache_bytes -= len(hit[1])
    sem = _semaphore()
    if not sem.acquire(timeout=timeout / 2):
        raise TileProxyBusyError
    try:
        resp = httpx.get(url, params=params, timeout=timeout)
    finally:
        sem.release()
    if resp.status_code == 200:
        _store(key, resp.content)
    return resp.status_code, resp.content
