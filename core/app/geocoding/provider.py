# SPDX-License-Identifier: Apache-2.0
"""Fournisseur de géocodage (REV-102). Une petite interface (Geocoder) et un
seul fournisseur, la BAN servie par la Géoplateforme (data.geopf.fr) :
api-adresse.data.gouv.fr est déprécié (sunset 2026-01-31) et redirige."""

import os
from collections.abc import Callable
from typing import Protocol

import httpx
from fastapi import HTTPException
from pydantic import BaseModel

from app.geocoding.egress import build_guarded_client

DEFAULT_GEOCODING_URL = "https://data.geopf.fr/geocodage/search"


class GeocodeResult(BaseModel):
    label: str
    lon: float
    lat: float


class Geocoder(Protocol):
    def search(self, q: str, limit: int) -> list[GeocodeResult]: ...


class BanGeocoder:
    def __init__(
        self, base_url: str, client_factory: Callable[[], httpx.Client] = build_guarded_client
    ):
        self._url = base_url
        self._client_factory = client_factory

    def search(self, q: str, limit: int) -> list[GeocodeResult]:
        with self._client_factory() as client:
            response = client.get(self._url, params={"q": q, "limit": limit})
        response.raise_for_status()
        return [
            GeocodeResult(
                label=f["properties"]["label"],
                lon=f["geometry"]["coordinates"][0],
                lat=f["geometry"]["coordinates"][1],
            )
            for f in response.json()["features"]
        ]


def get_geocoder() -> Geocoder:
    url = os.environ.get("CORE_GEOCODING_URL", DEFAULT_GEOCODING_URL)
    if not url:
        raise HTTPException(status_code=503, detail="Géocodage désactivé sur cette instance.")
    return BanGeocoder(url)
