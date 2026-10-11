# SPDX-License-Identifier: Apache-2.0
"""Fournisseur de géocodage (REV-102). Une petite interface (Geocoder) et deux
fournisseurs : la BAN servie par la Géoplateforme (data.geopf.fr, défaut ;
api-adresse.data.gouv.fr est déprécié, sunset 2026-01-31, et redirige) ou
Nominatim (CORE_GEOCODING_PROVIDER=nominatim). L'opérateur règle ensemble
fournisseur, CORE_GEOCODING_URL et CORE_GEOCODING_EGRESS_ALLOWLIST."""

import os
import time
from collections.abc import Callable
from typing import Protocol

import httpx
from fastapi import HTTPException
from pydantic import BaseModel

from app.geocoding.egress import build_guarded_client

DEFAULT_GEOCODING_URL = "https://data.geopf.fr/geocodage/search"
DEFAULT_NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"


# Borne de taille de la reponse amont (10 resultats = quelques Kio) ; refusee
# apres lecture (ValueError -> 502). ponytail: pas de lecture en flux, la
# garde d'egress + timeout 10 s limitent deja l'exposition.
MAX_RESPONSE_BYTES = 1_048_576


def _checked_json(response: httpx.Response):
    response.raise_for_status()
    if len(response.content) > MAX_RESPONSE_BYTES:
        raise ValueError("réponse de géocodage trop volumineuse")
    return response.json()


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
        return [
            GeocodeResult(
                label=f["properties"]["label"],
                lon=f["geometry"]["coordinates"][0],
                lat=f["geometry"]["coordinates"][1],
            )
            for f in _checked_json(response)["features"]
        ]


# Cache global (processus) des réponses Nominatim : la politique d'usage OSM
# impose <= 1 req/s, une même adresse n'a pas à retourner à l'amont.
# ponytail: par processus, FIFO borné ; cache partagé si plusieurs réplicas pèsent.
_NOMINATIM_CACHE_TTL_S = 3600
_NOMINATIM_CACHE_MAX = 512
_nominatim_cache: dict[tuple[str, str, int], tuple[float, list[GeocodeResult]]] = {}


def nominatim_user_agent() -> str:
    return os.environ.get("CORE_GEOCODING_USER_AGENT") or "GeoStudio/1 (geocoding)"


class NominatimGeocoder:
    def __init__(
        self, base_url: str, client_factory: Callable[[], httpx.Client] = build_guarded_client
    ):
        self._url = base_url
        self._client_factory = client_factory

    def search(self, q: str, limit: int) -> list[GeocodeResult]:
        key = (self._url, q.strip().lower(), limit)
        hit = _nominatim_cache.get(key)
        if hit and time.monotonic() - hit[0] < _NOMINATIM_CACHE_TTL_S:
            return hit[1]
        with self._client_factory() as client:
            response = client.get(
                self._url,
                params={"q": q, "format": "jsonv2", "limit": limit},
                # Nominatim (politique d'usage OSM) exige un User-Agent identifiant :
                # CORE_GEOCODING_USER_AGENT (contact de l'opérateur), sinon un défaut.
                headers={"User-Agent": nominatim_user_agent()},
            )
        results = [
            GeocodeResult(label=i["display_name"], lon=float(i["lon"]), lat=float(i["lat"]))
            for i in _checked_json(response)
        ]
        if len(_nominatim_cache) >= _NOMINATIM_CACHE_MAX:
            _nominatim_cache.pop(next(iter(_nominatim_cache)))
        _nominatim_cache[key] = (time.monotonic(), results)
        return results


def get_geocoder() -> Geocoder:
    provider = os.environ.get("CORE_GEOCODING_PROVIDER", "ban") or "ban"
    if provider not in ("ban", "nominatim"):
        raise HTTPException(
            status_code=503,
            detail=f"Fournisseur de géocodage inconnu : {provider!r} (attendu : ban ou nominatim).",
        )
    if provider == "nominatim" and not os.environ.get("CORE_GEOCODING_URL"):
        # Pas de repli silencieux sur l'instance publique OSM (REV-323 B) :
        # l'opérateur choisit son instance (la publique = DEFAULT_NOMINATIM_URL).
        raise HTTPException(
            status_code=503,
            detail="CORE_GEOCODING_URL est requis avec le fournisseur nominatim.",
        )
    url = os.environ.get("CORE_GEOCODING_URL", DEFAULT_GEOCODING_URL)
    if not url:
        raise HTTPException(status_code=503, detail="Géocodage désactivé sur cette instance.")
    return NominatimGeocoder(url) if provider == "nominatim" else BanGeocoder(url)
