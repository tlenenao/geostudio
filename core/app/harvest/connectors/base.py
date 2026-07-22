# SPDX-License-Identifier: Apache-2.0
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class HarvestedRecord:
    external_id: str
    title: str
    abstract: str
    keywords: list[str]
    bbox: list[float]
    external_url: str
    items_url: str | None


class HarvestConnector(Protocol):
    type: str
    supports_copy: bool

    def fetch(self, url: str) -> Iterable[HarvestedRecord]: ...
