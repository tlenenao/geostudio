# SPDX-License-Identifier: Apache-2.0
"""Géocodage par lot (ARC-03) : N adresses -> N lignes, jamais d'exception par
ligne. Concurrence bornée + cadence plafonnée (BAN publique : 50 req/s/IP)."""

import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Literal

from pydantic import BaseModel

from app.geocoding.provider import Geocoder
from app.ratelimit.limiter import pg_long_hit, shared_engine

MAX_BATCH = 500
# Sous le plafond amont de 50 req/s/IP, marge pour les autres usages de l'instance.
MAX_PER_SECOND = 40.0
_WORKERS = 8


class BatchRow(BaseModel):
    address: str
    status: Literal["trouvé", "non_trouvé", "erreur"]
    label: str | None = None
    lon: float | None = None
    lat: float | None = None


class _Pacer:
    def __init__(
        self,
        per_second: float,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        shared: bool = False,
    ):
        self._step, self._clock, self._sleep = 1.0 / per_second, clock, sleep
        self._per_second, self._shared = per_second, shared
        self._next = 0.0
        self._lock = threading.Lock()

    def wait(self) -> None:
        with self._lock:
            now = self._clock()
            slot = max(now, self._next)
            self._next = slot + self._step
        if slot > now:
            self._sleep(slot - now)
        if self._shared:
            self._wait_shared()

    def _wait_shared(self) -> None:
        """REV-398 : plafond par seconde commun à tous les process (core, worker) qui partagent
        l'IP sortante : un compteur Postgres par seconde ; base HS, cadence locale seule."""
        engine = shared_engine()
        while engine is not None:
            sec = int(time.time())
            try:
                if pg_long_hit(engine, "geocode:long", "ban", sec) <= self._per_second:
                    return
            except Exception:  # noqa: BLE001 — repli sur la cadence du process
                return
            self._sleep(sec + 1 - time.time())


# Cadence amont partagée par REST et MCP (BAN : 50 req/s/IP, donc par process),
# et un seul lot à la fois par process.
# Cadence : partagée entre process via Postgres (`_wait_shared`) ; le verrou « un lot à la
# fois » reste par process (il borne la mémoire/les threads, pas le débit amont).
_PACER = _Pacer(MAX_PER_SECOND, shared=True)
_BATCH_LOCK = threading.Lock()


class BatchBusy(Exception):
    """Un autre lot de géocodage tourne déjà dans ce process."""


def geocode_batch(
    geocoder: Geocoder,
    addresses: list[str],
    *,
    per_second: float | None = None,
) -> list[BatchRow]:
    if not _BATCH_LOCK.acquire(blocking=False):
        raise BatchBusy
    try:
        return _run(geocoder, addresses, _PACER if per_second is None else _Pacer(per_second))
    finally:
        _BATCH_LOCK.release()


def _run(geocoder: Geocoder, addresses: list[str], pacer: _Pacer) -> list[BatchRow]:

    def one(address: str) -> BatchRow:
        pacer.wait()
        try:
            hits = geocoder.search(address, 1)
        except Exception:  # noqa: BLE001 — une ligne en échec ne perd pas le lot
            return BatchRow(address=address, status="erreur")
        if not hits:
            return BatchRow(address=address, status="non_trouvé")
        h = hits[0]
        return BatchRow(address=address, status="trouvé", label=h.label, lon=h.lon, lat=h.lat)

    with ThreadPoolExecutor(max_workers=_WORKERS) as pool:
        return list(pool.map(one, addresses))
