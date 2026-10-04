# SPDX-License-Identifier: Apache-2.0
"""GET /v1/geocode (REV-102) : proxy authentifié vers le fournisseur de
géocodage. Le navigateur ne parle qu'au cœur (pas de changement CSP
connect-src) ; groupe de rate limit dédié « geocode »."""

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.auth.dependency import get_current_user
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
    geocoder: Geocoder = Depends(get_geocoder),
    _user: User = Depends(get_current_user),
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
