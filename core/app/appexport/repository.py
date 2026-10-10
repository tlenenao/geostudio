# SPDX-License-Identifier: Apache-2.0
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.appexport.models import AppExportJob


def _now() -> datetime:
    return datetime.now(UTC)


# Même discipline de reclaim-par-âge que app.export.repository (anchored on
# started_at, jamais created_at — un job resté "pending" en file avant de
# démarrer ne doit pas être réclamé dès qu'il passe "running").
_RUNNING_RECLAIM_MINUTES = 60
_TERMINAL = ("done", "error")


def create_job(
    session: Session,
    *,
    tenant_id: str,
    item_id: str,
    user_id: str,
    mode: str,
) -> AppExportJob:
    job = AppExportJob(
        id=uuid.uuid4().hex,
        tenant_id=tenant_id,
        item_id=item_id,
        user_id=user_id,
        mode=mode,
        status="pending",
    )
    session.add(job)
    session.flush()
    session.refresh(job)
    return job


def get_job(session: Session, *, tenant_id: str, job_id: str) -> AppExportJob | None:
    return session.execute(
        select(AppExportJob).where(AppExportJob.id == job_id, AppExportJob.tenant_id == tenant_id)
    ).scalar_one_or_none()


def mark_running(session: Session, *, job_id: str) -> bool:
    """REV-295 : transition conditionnelle `pending -> running` (jumelle de
    pipelines.repository.mark_running). False si le job n'est plus prenable
    (terminé, en erreur, déjà pris, inconnu) : l'appelant sort sans exécuter."""
    result = session.execute(
        update(AppExportJob)
        .where(AppExportJob.id == job_id, AppExportJob.status == "pending")
        .values(status="running", started_at=_now())
    )
    session.flush()
    return bool(result.rowcount)  # type: ignore[attr-defined]


def mark_done(
    session: Session,
    *,
    job_id: str,
    result_key: str,
    byte_size: int | None = None,
    warning: str | None = None,
) -> None:
    # `warning` (ex. troncature, j10b-005) est stocké dans `error` : un job
    # « done » avec `error` renseigné = terminé avec avertissement (aucune
    # migration ; le shell l'affiche à côté du lien de téléchargement).
    # c02-006 : UPDATE conditionnel — un job déjà clos (réclamé en erreur par le
    # balayage) ne repasse jamais « done ».
    session.execute(
        update(AppExportJob)
        .where(AppExportJob.id == job_id, AppExportJob.status.notin_(_TERMINAL))
        .values(
            status="done",
            result_key=result_key,
            byte_size=byte_size,
            error=warning,
            finished_at=_now(),
        )
    )
    session.flush()


def mark_error(session: Session, *, job_id: str, error: str) -> None:
    session.execute(
        update(AppExportJob)
        .where(AppExportJob.id == job_id, AppExportJob.status.notin_(_TERMINAL))
        .values(status="error", error=error, finished_at=_now())
    )
    session.flush()


def reclaim_stuck_jobs(
    session: Session, *, older_than_minutes: int = _RUNNING_RECLAIM_MINUTES
) -> list[str]:
    threshold = _now() - timedelta(minutes=older_than_minutes)
    rows = (
        session.execute(select(AppExportJob).where(AppExportJob.status.in_(("pending", "running"))))
        .scalars()
        .all()
    )
    reclaimed: list[str] = []
    for job in rows:
        # P01.04 : « pending » (jamais démarré : defer perdu, file non
        # consommée) s'ancre sur created_at, « running » sur started_at.
        started_at = job.started_at if job.status == "running" else job.created_at
        if started_at is None:
            continue
        if started_at.tzinfo is None:
            started_at = started_at.replace(tzinfo=UTC)
        if started_at >= threshold:
            continue
        # c02-006 : conditionnel sur le statut lu — un « done » committé entre
        # la lecture et l'écriture n'est pas écrasé.
        claimed = session.execute(
            update(AppExportJob)
            .where(AppExportJob.id == job.id, AppExportJob.status == job.status)
            .values(
                status="error",
                error="app export timed out (worker crashed or hung)",
                finished_at=_now(),
            )
        )
        if claimed.rowcount:  # type: ignore[attr-defined]
            reclaimed.append(job.id)
    if reclaimed:
        session.flush()
    return reclaimed
