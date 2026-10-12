# SPDX-License-Identifier: Apache-2.0
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.export.models import ExportJob
from app.job_timeouts import running_reclaim_minutes


def _now() -> datetime:
    return datetime.now(UTC)


# Même discipline de reclaim-par-âge que app.pipelines.repository
# (_RUNNING_RECLAIM_MINUTES) / app.alerts.repository (_PENDING_RECLAIM_MINUTES) :
# un job resté "running" plus vieux que ce délai est présumé planté
# (export-worker/Chromium tué en cours de rendu, OOM notamment — cf. revue
# finale SP-17a, I7). L'appelant périodique est
# app.reports.jobs._trigger_due_reports, à la fin de chaque tick du balayage
# des rapports planifiés (SP-17b). Ancre
# started_at (posé par mark_running), jamais created_at : un job resté
# longtemps "pending" en file avant de démarrer ne doit pas être réclamé dès
# qu'il passe "running".
_TERMINAL = ("done", "error", "cancelled")


def create_job(
    session: Session,
    *,
    tenant_id: str,
    item_id: str,
    user_id: str,
    format: str,
    page_id: str | None = None,
    ctx: str | None = None,
) -> ExportJob:
    job = ExportJob(
        id=uuid.uuid4().hex,
        tenant_id=tenant_id,
        item_id=item_id,
        user_id=user_id,
        format=format,
        status="pending",
        page_id=page_id,
        ctx=ctx,
    )
    session.add(job)
    session.flush()
    session.refresh(job)
    return job


def get_job(session: Session, *, tenant_id: str, job_id: str) -> ExportJob | None:
    return session.execute(
        select(ExportJob).where(ExportJob.id == job_id, ExportJob.tenant_id == tenant_id)
    ).scalar_one_or_none()


def mark_running(session: Session, *, job_id: str) -> bool:
    """REV-295 : transition conditionnelle `pending -> running` (jumelle de
    pipelines.repository.mark_running). False si le job n'est plus prenable
    (terminé, en erreur, déjà pris, inconnu) : l'appelant sort sans exécuter."""
    result = session.execute(
        update(ExportJob)
        .where(ExportJob.id == job_id, ExportJob.status == "pending")
        .values(status="running", started_at=_now())
    )
    session.flush()
    return bool(result.rowcount)  # type: ignore[attr-defined]


def mark_done(
    session: Session, *, job_id: str, result_key: str, byte_size: int | None = None
) -> bool:
    # c02-006 : UPDATE conditionnel — un job déjà clos (réclamé en erreur par le
    # balayage) ne repasse jamais « done ».
    result = session.execute(
        update(ExportJob)
        .where(
            ExportJob.id == job_id,
            ExportJob.status.notin_((*_TERMINAL, "cancel_requested")),
        )
        .values(status="done", result_key=result_key, byte_size=byte_size, finished_at=_now())
    )
    session.flush()
    return bool(result.rowcount)  # type: ignore[attr-defined]


def request_cancel(session: Session, *, job_id: str) -> str | None:
    """ARC-16 (jumelle de ingestion.repository.request_cancel, D6) : `pending ->
    cancelled` (le worker ne le prendra plus) ou `running -> cancel_requested`
    (testé par le worker avant le lancement et avant l'envoi : le rendu Chromium
    lui-même n'est pas interruptible, borné à RENDER_TIMEOUT_MS). Renvoie le
    nouveau statut, None si le job n'est plus annulable."""
    for src, dst in (("pending", "cancelled"), ("running", "cancel_requested")):
        result = session.execute(
            update(ExportJob)
            .where(ExportJob.id == job_id, ExportJob.status == src)
            .values(status=dst)
        )
        session.flush()
        if result.rowcount:  # type: ignore[attr-defined]
            if dst == "cancelled":
                session.execute(
                    update(ExportJob).where(ExportJob.id == job_id).values(finished_at=_now())
                )
            return dst
    return None


def is_cancel_requested(session: Session, *, job_id: str) -> bool:
    status = session.execute(select(ExportJob.status).where(ExportJob.id == job_id)).scalar()
    return status == "cancel_requested"


def mark_cancelled(session: Session, *, job_id: str) -> None:
    session.execute(
        update(ExportJob)
        .where(ExportJob.id == job_id, ExportJob.status == "cancel_requested")
        .values(status="cancelled", finished_at=_now())
    )
    session.flush()


def mark_error(session: Session, *, job_id: str, error: str) -> None:
    session.execute(
        update(ExportJob)
        .where(ExportJob.id == job_id, ExportJob.status.notin_(_TERMINAL))
        .values(status="error", error=error, finished_at=_now())
    )
    session.flush()


def reclaim_stuck_jobs(session: Session, *, older_than_minutes: int | None = None) -> list[str]:
    """Marque "error" tout export_jobs resté "running" plus vieux que
    older_than_minutes (ancré sur started_at) — cf. la note de module sur
    _RUNNING_RECLAIM_MINUTES. Retourne les ids réclamés. Cross-tenant par
    construction (comme app.pipelines.repository.list_due_pipelines /
    app.alerts.repository.list_due_rules) : appelée une fois pour tous les
    tenants, pas par tenant. Câblée en fin de tick par
    app.reports.jobs._trigger_due_reports (SP-17b) — docstring corrigée
    SP-49, elle affirmait encore à tort qu'aucun appelant périodique
    n'existait (stale depuis le câblage, cf. aussi le docstring périmé
    équivalent dans tests/test_export_repository.py)."""
    threshold = _now() - timedelta(minutes=older_than_minutes or running_reclaim_minutes())
    rows = (
        session.execute(
            select(ExportJob).where(
                ExportJob.status.in_(("pending", "running", "cancel_requested"))
            )
        )
        .scalars()
        .all()
    )
    reclaimed: list[str] = []
    for job in rows:
        # P01.04 : « pending » (jamais démarré : defer perdu, file non
        # consommée) s'ancre sur created_at, « running » sur started_at.
        started_at = job.started_at if job.status != "pending" else job.created_at
        if started_at is None:
            continue
        if started_at.tzinfo is None:
            started_at = started_at.replace(tzinfo=UTC)
        if started_at >= threshold:
            continue
        # c02-006 : conditionnel sur le statut lu — un « done » committé entre
        # la lecture et l'écriture n'est pas écrasé.
        claimed = session.execute(
            update(ExportJob)
            .where(ExportJob.id == job.id, ExportJob.status == job.status)
            .values(
                status="error",
                error="export timed out (worker crashed or hung)",
                finished_at=_now(),
            )
        )
        if claimed.rowcount:  # type: ignore[attr-defined]
            reclaimed.append(job.id)
    if reclaimed:
        session.flush()
    return reclaimed
