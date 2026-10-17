# SPDX-License-Identifier: Apache-2.0
"""GET /v1/geocode (REV-102) : proxy authentifié vers le fournisseur de
géocodage. Le navigateur ne parle qu'au cœur (pas de changement CSP
connect-src) ; groupe de rate limit dédié « geocode »."""

import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth.dependency import get_current_user
from app.db import get_session
from app.geocoding import jobs as geocode_jobs
from app.geocoding.batch import MAX_BATCH, BatchBusy, BatchRow, geocode_batch
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
    try:
        rows = geocode_batch(geocoder, body.addresses)
    except BatchBusy:
        raise HTTPException(
            status_code=429, detail="Un lot de géocodage est déjà en cours, réessayez."
        ) from None
    errors = sum(r.status == "erreur" for r in rows)
    if errors == len(rows):  # amont injoignable/bloqué : même 502 que GET /geocode
        raise HTTPException(status_code=502, detail="Le service de géocodage est indisponible.")
    return BatchResponse(
        results=rows,
        found=sum(r.status == "trouvé" for r in rows),
        not_found=sum(r.status == "non_trouvé" for r in rows),
        errors=errors,
    )


class GeocodeJobRequest(BaseModel):
    addresses: list[str] = Field(min_length=1, max_length=geocode_jobs.MAX_JOB_ADDRESSES)


class GeocodeJobOut(BaseModel):
    id: str
    status: str
    total: int
    processed: int
    found: int
    not_found: int
    errors: int
    error: str | None = None
    results: list[BatchRow] | None = None  # présents seulement une fois le job terminé


def _job_out(job) -> GeocodeJobOut:
    rows = [BatchRow(**r) for r in job.results]
    done = job.status == "succeeded"
    return GeocodeJobOut(
        id=job.id,
        status=job.status,
        total=len(job.addresses),
        processed=len(rows),
        found=sum(r.status == "trouvé" for r in rows),
        not_found=sum(r.status == "non_trouvé" for r in rows),
        errors=sum(r.status == "erreur" for r in rows),
        error=job.error,
        results=rows if done else None,
    )


@router.post("/jobs", response_model=GeocodeJobOut, status_code=202)
def create_geocode_job(
    body: GeocodeJobRequest,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> GeocodeJobOut:
    """Lot asynchrone avec reprise (REV-367 j) : jusqu'à 5000 adresses, progression
    par GET /geocode/jobs/{id}. Le POST /batch synchrone reste pour <= 500."""
    if any(not 3 <= len(a) <= 200 for a in body.addresses):
        raise HTTPException(status_code=422, detail="Chaque adresse doit faire 3 à 200 caractères.")
    active = geocode_jobs.count_active_jobs(session, tenant_id=user.tenant_id, user_id=user.id)
    if active >= geocode_jobs.MAX_ACTIVE_JOBS_PER_USER:  # AUD-156
        raise HTTPException(
            status_code=429, detail="Trop de lots de géocodage en cours, réessayez plus tard."
        )
    job = geocode_jobs.create_job(
        session, tenant_id=user.tenant_id, user_id=user.id, addresses=body.addresses
    )
    out = _job_out(job)
    session.commit()  # commit avant defer ; sinon le balayage reprend le job `pending`
    try:
        geocode_jobs.run_geocode_job.defer(job_id=job.id, tenant_id=user.tenant_id)
    except Exception:
        logging.getLogger(__name__).exception("geocode job %s : defer échoué", job.id)
    return out


@router.get("/jobs/{job_id}", response_model=GeocodeJobOut)
def get_geocode_job(
    job_id: str,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> GeocodeJobOut:
    job = geocode_jobs.get_job(session, job_id, user.tenant_id)
    if job is None or job.created_by != user.id:
        raise HTTPException(status_code=404, detail="Job de géocodage introuvable.")
    return _job_out(job)


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
