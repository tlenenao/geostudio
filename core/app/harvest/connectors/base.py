# SPDX-License-Identifier: Apache-2.0
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol

import httpx


@dataclass(frozen=True)
class HarvestedRecord:
    external_id: str
    title: str
    abstract: str
    keywords: list[str]
    bbox: list[float]
    external_url: str
    items_url: str | None
    raster_tiles_url: str | None = None
    copy_filename: str | None = None


class HarvestConnector(Protocol):
    type: str
    supports_copy: bool

    def fetch(self, url: str) -> Iterable[HarvestedRecord]: ...

    def fetch_copy_geojson(
        self, record: HarvestedRecord, *, http_get: "HttpGet"
    ) -> bytes | None: ...


# Getter HTTP gardé injecté par le moteur (egress.guarded_get en prod, un fake
# retournant des httpx.Response en test). Lève EgressBlockedError sur cible
# interne — non capturé par les connecteurs, propagé jusqu'au moteur.
class HttpGet(Protocol):
    def __call__(self, url: str) -> httpx.Response: ...
