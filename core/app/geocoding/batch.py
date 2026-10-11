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
    ):
        self._step, self._clock, self._sleep = 1.0 / per_second, clock, sleep
        self._next = 0.0
        self._lock = threading.Lock()

    def wait(self) -> None:
        with self._lock:
            now = self._clock()
            slot = max(now, self._next)
            self._next = slot + self._step
        if slot > now:
            self._sleep(slot - now)


def geocode_batch(
    geocoder: Geocoder,
    addresses: list[str],
    *,
    per_second: float = MAX_PER_SECOND,
    sleep: Callable[[float], None] = time.sleep,
) -> list[BatchRow]:
    pacer = _Pacer(per_second, sleep=sleep)

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
