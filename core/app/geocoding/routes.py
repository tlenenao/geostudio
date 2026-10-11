# SPDX-License-Identifier: Apache-2.0
"""GET /v1/geocode (REV-102) : proxy authentifié vers le fournisseur de
géocodage. Le navigateur ne parle qu'au cœur (pas de changement CSP
connect-src) ; groupe de rate limit dédié « geocode »."""

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.auth.dependency import get_current_user
from app.geocoding.batch import MAX_BATCH, BatchRow, geocode_batch
from app.geocoding.egress import EgressBlockedError
from app.geocoding.provider import Geocoder, GeocodeResult, get_geocoder
from app.users.models import User

router = APIRouter(prefix="/geocode", tags=["geocoding"])


class GeocodeResponse(BaseModel):
    results: list[GeocodeResult]


@router.get("", response_model=GeocodeResponse)
def geocode(
    q: str = Query(min_length=3, max_length=200),
    limit: int = Query(default=5, ge=1, le=10),
    _user: User = Depends(get_current_user),
    geocoder: Geocoder = Depends(get_geocoder),
) -> GeocodeResponse:
    try:
        return GeocodeResponse(results=geocoder.search(q, limit))
    # Réponse amont illisible (JSON invalide, feature sans géométrie) = même
    # 502 que l'amont injoignable : jamais de 500 ni de fuite réseau interne.
    except (
        EgressBlockedError,
        httpx.HTTPError,
        KeyError,
        IndexError,
        TypeError,
        ValueError,
    ) as exc:
        raise HTTPException(
            status_code=502, detail="Le service de géocodage est indisponible."
        ) from exc


class BatchRequest(BaseModel):
    addresses: list[str] = Field(min_length=1, max_length=MAX_BATCH)


class BatchResponse(BaseModel):
    results: list[BatchRow]
    found: int
    not_found: int
    errors: int


@router.post("/batch", response_model=BatchResponse)
def geocode_many(
    body: BatchRequest,
    _user: User = Depends(get_current_user),
    geocoder: Geocoder = Depends(get_geocoder),
) -> BatchResponse:
    # ponytail: synchrone (500 adresses ~ 15 s à 40 req/s), pas de table de job
    # (migration non autorisée sur cette voie) ; job + reprise = vague 1.
    if any(not 3 <= len(a) <= 200 for a in body.addresses):
        raise HTTPException(status_code=422, detail="Chaque adresse doit faire 3 à 200 caractères.")
    rows = geocode_batch(geocoder, body.addresses)
    errors = sum(r.status == "erreur" for r in rows)
    if errors == len(rows):  # amont injoignable/bloqué : même 502 que GET /geocode
        raise HTTPException(status_code=502, detail="Le service de géocodage est indisponible.")
    return BatchResponse(
        results=rows,
        found=sum(r.status == "trouvé" for r in rows),
        not_found=sum(r.status == "non_trouvé" for r in rows),
        errors=errors,
    )


class ReverseResponse(BaseModel):
    result: GeocodeResult | None


@router.get("/reverse", response_model=ReverseResponse)
def reverse_geocode(
    lon: float = Query(ge=-180, le=180),
    lat: float = Query(ge=-90, le=90),
    _user: User = Depends(get_current_user),
    geocoder: Geocoder = Depends(get_geocoder),
) -> ReverseResponse:
    try:
        return ReverseResponse(result=geocoder.reverse(lon, lat))
    except (
        EgressBlockedError,
        httpx.HTTPError,
        KeyError,
        IndexError,
        TypeError,
        ValueError,
    ) as exc:
        raise HTTPException(
            status_code=502, detail="Le service de géocodage est indisponible."
        ) from exc
