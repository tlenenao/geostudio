# SPDX-License-Identifier: Apache-2.0
"""Fournisseur de géocodage (REV-102). Une petite interface (Geocoder) et deux
fournisseurs : la BAN servie par la Géoplateforme (data.geopf.fr, défaut ;
api-adresse.data.gouv.fr est déprécié, sunset 2026-01-31, et redirige) ou
Nominatim (CORE_GEOCODING_PROVIDER=nominatim). L'opérateur règle ensemble
fournisseur, CORE_GEOCODING_URL et CORE_GEOCODING_EGRESS_ALLOWLIST."""

import os
from collections.abc import Callable
from typing import Protocol

import httpx
from fastapi import HTTPException
from pydantic import BaseModel

from app.geocoding.egress import build_guarded_client

DEFAULT_GEOCODING_URL = "https://data.geopf.fr/geocodage/search"
DEFAULT_NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"


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


class NominatimGeocoder:
    def __init__(
        self, base_url: str, client_factory: Callable[[], httpx.Client] = build_guarded_client
    ):
        self._url = base_url
        self._client_factory = client_factory

    def search(self, q: str, limit: int) -> list[GeocodeResult]:
        with self._client_factory() as client:
            response = client.get(
                self._url,
                params={"q": q, "format": "jsonv2", "limit": limit},
                # Nominatim (politique d'usage OSM) exige un User-Agent identifiant.
                headers={"User-Agent": "GeoStudio/1 (geocoding)"},
            )
        response.raise_for_status()
        return [
            GeocodeResult(label=i["display_name"], lon=float(i["lon"]), lat=float(i["lat"]))
            for i in response.json()
        ]


def get_geocoder() -> Geocoder:
    provider = os.environ.get("CORE_GEOCODING_PROVIDER", "ban") or "ban"
    if provider not in ("ban", "nominatim"):
        raise HTTPException(
            status_code=503,
            detail=f"Fournisseur de géocodage inconnu : {provider!r} (attendu : ban ou nominatim).",
        )
    default = DEFAULT_NOMINATIM_URL if provider == "nominatim" else DEFAULT_GEOCODING_URL
    url = os.environ.get("CORE_GEOCODING_URL", default)
    if not url:
        raise HTTPException(status_code=503, detail="Géocodage désactivé sur cette instance.")
    return NominatimGeocoder(url) if provider == "nominatim" else BanGeocoder(url)
