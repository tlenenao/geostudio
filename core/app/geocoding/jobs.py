# SPDX-License-Identifier: Apache-2.0
"""Géocodage par lot asynchrone avec reprise (REV-367 j).

Le job traite `addresses` par tranches de `CHUNK` ; chaque tranche est commitée
(`results` + `updated_at` servent de battement de coeur). Un worker tué laisse un
job `running` périmé : le balayage le repasse `pending` et le redéfère, la
reprise repart de `len(results)` (piège n°14 : commit puis defer = balayage).
File `dataexport` réutilisée (déjà câblée dans le worker : pas de nouvelle file)."""

import logging
import time
import uuid
from datetime import datetime, timedelta

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.auth.dependency import is_read_only_mode
from app.db import request_scoped_session
from app.geocoding.batch import BatchBusy, geocode_batch
from app.geocoding.models import GeocodeJob, _now
from app.geocoding.provider import get_geocoder
from app.job_errors import public_error
from app.jobs import app
from app.jobs.engine import session_factory

logger = logging.getLogger(__name__)

MAX_JOB_ADDRESSES = 5000
CHUNK = 100
STALE_MINUTES = 5
# AUD-156 : lots simultanés par utilisateur, et rétention des lots terminés
# (les adresses sont une donnée personnelle potentielle).
MAX_ACTIVE_JOBS_PER_USER = 3
RETENTION_DAYS = 7


class GeocoderBusy(RuntimeError):
    """Refus métier lisible par l'utilisateur (le reste du catch-all est générique, AUD-100)."""


def create_job(
    session: Session, *, tenant_id: str, user_id: str, addresses: list[str]
) -> GeocodeJob:
    job = GeocodeJob(
        id=uuid.uuid4().hex,
        tenant_id=tenant_id,
        created_by=user_id,
        status="pending",
        addresses=addresses,
        results=[],
    )
    session.add(job)
    session.flush()
    return job


def count_active_jobs(session: Session, *, tenant_id: str, user_id: str) -> int:
    return (
        session.scalar(
            select(func.count())
            .select_from(GeocodeJob)
            .where(
                GeocodeJob.tenant_id == tenant_id,
                GeocodeJob.created_by == user_id,
                GeocodeJob.status.in_(("pending", "running")),
            )
        )
        or 0
    )


def purge_finished_jobs(session: Session, *, now: datetime) -> int:
    result = session.execute(
        delete(GeocodeJob).where(
            GeocodeJob.status.in_(("succeeded", "failed")),
            GeocodeJob.updated_at < now - timedelta(days=RETENTION_DAYS),
        )
    )
    return result.rowcount or 0  # type: ignore[attr-defined]


def get_job(session: Session, job_id: str, tenant_id: str) -> GeocodeJob | None:
    return session.execute(
        select(GeocodeJob).where(GeocodeJob.id == job_id, GeocodeJob.tenant_id == tenant_id)
    ).scalar_one_or_none()


def _take(session: Session, job_id: str) -> bool:
    """pending -> running (UPDATE conditionnel : un double defer est inoffensif)."""
    res = session.execute(
        update(GeocodeJob)
        .where(GeocodeJob.id == job_id, GeocodeJob.status == "pending")
        .values(status="running", updated_at=_now())
    )
    return bool(res.rowcount)  # type: ignore[attr-defined]


@app.task(queue="dataexport")
def run_geocode_job(job_id: str, tenant_id: str) -> None:
    factory = session_factory()
    with request_scoped_session(factory) as session:
        job = get_job(session, job_id, tenant_id)
        if job is None or not _take(session, job_id):
            return
        addresses = list(job.addresses)
        done = list(job.results)
    geocoder = get_geocoder()
    try:
        while len(done) < len(addresses):
            chunk = addresses[len(done) : len(done) + CHUNK]
            for _ in range(60):  # un lot à la fois par process : on attend notre tour
                try:
                    rows = geocode_batch(geocoder, chunk)
                    break
                except BatchBusy:
                    time.sleep(1)
            else:
                raise GeocoderBusy("géocodeur occupé, lot à relancer plus tard")
            done.extend(r.model_dump() for r in rows)
            # ponytail: réécrit tout `results` à chaque tranche (O(n²) borné par
            # MAX_JOB_ADDRESSES / CHUNK = 50 écritures) ; table de lignes si le plafond monte.
            with request_scoped_session(factory) as session:
                session.execute(
                    update(GeocodeJob)
                    .where(GeocodeJob.id == job_id, GeocodeJob.status == "running")
                    .values(results=done, updated_at=_now())
                )
    except Exception as exc:
        logger.exception("geocode job %s : échec", job_id)
        with request_scoped_session(factory) as session:
            session.execute(
                update(GeocodeJob)
                .where(GeocodeJob.id == job_id, GeocodeJob.status == "running")
                .values(
                    status="failed",
                    error=public_error(exc, user_errors=(GeocoderBusy,)),
                    updated_at=_now(),
                )
            )
        return
    with request_scoped_session(factory) as session:
        session.execute(
            update(GeocodeJob)
            .where(GeocodeJob.id == job_id, GeocodeJob.status == "running")
            .values(status="succeeded", updated_at=_now())
        )


def requeue_stale(session: Session) -> list[tuple[str, str]]:
    """`pending` ou `running` sans battement depuis STALE_MINUTES -> (re)déférables.
    Les `running` périmés repassent `pending` (compare-and-swap sur updated_at)."""
    threshold = _now() - timedelta(minutes=STALE_MINUTES)
    rows = session.execute(
        select(GeocodeJob.id, GeocodeJob.tenant_id, GeocodeJob.status, GeocodeJob.updated_at)
        .where(GeocodeJob.status.in_(("pending", "running")), GeocodeJob.updated_at < threshold)
        .limit(100)
    ).all()
    out: list[tuple[str, str]] = []
    for job_id, tenant_id, status, updated_at in rows:
        if status == "running":
            claimed = session.execute(
                update(GeocodeJob)
                .where(
                    GeocodeJob.id == job_id,
                    GeocodeJob.status == "running",
                    GeocodeJob.updated_at == updated_at,
                )
                .values(status="pending", updated_at=_now())
            )
            if not claimed.rowcount:  # type: ignore[attr-defined]
                continue
        else:
            session.execute(
                update(GeocodeJob).where(GeocodeJob.id == job_id).values(updated_at=_now())
            )
        out.append((job_id, tenant_id))
    return out


@app.periodic(cron="*/10 * * * *")
@app.task(queue="dataexport", queueing_lock="sweep_geocode_jobs_task")
def sweep_geocode_jobs_task(timestamp: int) -> None:
    if is_read_only_mode():
        return
    with request_scoped_session(session_factory()) as session:
        stale = requeue_stale(session)
        purged = purge_finished_jobs(session, now=_now())
    if purged:
        logger.info("geocode : %d lot(s) terminé(s) purgé(s)", purged)
    for job_id, tenant_id in stale:
        try:
            run_geocode_job.defer(job_id=job_id, tenant_id=tenant_id)
        except Exception:
            logger.exception("geocode job %s : redefer impossible", job_id)
