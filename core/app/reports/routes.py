# SPDX-License-Identifier: Apache-2.0
"""Routes REST pour ReportSchedule (SP-17b §3) — le CRUD en lui-même passe
entièrement par les routes génériques /configs (kind="report"), comme pour
AlertRule/Pipeline ; ce module ne porte que l'unique lecture sur mesure,
reproduisant GET /alerts/{id}/evaluations."""

import os

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.dependency import get_current_user
from app.db import get_session
from app.export import repository as export_repo
from app.ingestion.routes import get_s3_client
from app.ingestion.storage import generate_presigned_get_url
from app.items import repository as items_repo
from app.reports import repository as reports_repo
from app.sharing.authorization import can
from app.users.models import User

router = APIRouter()


class ReportRunStatus(BaseModel):
    id: str
    status: str
    resultUrl: str | None
    error: str | None
    notifiedAt: str | None
    createdAt: str


def get_exports_bucket() -> str:
    # Même corps qu'app.export.routes.get_exports_bucket, redéclaré ici plutôt
    # qu'importé pour ne pas dépendre d'un module optionnel (le routeur export
    # n'est monté que si CORE_EXPORT_ENABLED). Ce sont donc DEUX clés
    # d'override distinctes, et app.main n'override que celle d'app.export —
    # sans conséquence : la valeur est lue dans l'environnement à chaque
    # appel, exactement comme le fait l'override.
    return os.environ.get("S3_EXPORTS_BUCKET", "geostudio-exports")


def _require_report_read_access(session: Session, *, user: User, item_id: str) -> None:
    facts = items_repo.get_access_facts(session, tenant_id=user.tenant_id, item_id=item_id)
    if facts is None or not can(session, user_id=user.id, action="read", item=facts):
        raise HTTPException(status_code=404, detail="report schedule not found")


@router.get("/reports/{item_id}/runs", response_model=list[ReportRunStatus])
def get_report_runs_route(
    item_id: str,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
    s3=Depends(get_s3_client),
    bucket: str = Depends(get_exports_bucket),
) -> list[ReportRunStatus]:
    _require_report_read_access(session, user=user, item_id=item_id)
    runs = reports_repo.list_runs(session, tenant_id=user.tenant_id, report_item_id=item_id)
    result: list[ReportRunStatus] = []
    for run in runs:
        if run.export_job_id is None:
            # Déclenchement échoué (revue finale SP-17b, I2) : la ligne existe
            # uniquement pour que la cadence cron soit mesurable, il n'y a
            # jamais eu d'export_jobs derrière. Le détail de l'échec est dans
            # le journal d'audit (action report.run).
            result.append(
                ReportRunStatus(
                    id=run.id,
                    status="error",
                    resultUrl=None,
                    error="déclenchement échoué (voir le journal d'audit)",
                    notifiedAt=run.notified_at.isoformat() if run.notified_at else None,
                    createdAt=run.created_at.isoformat(),
                )
            )
            continue
        job = export_repo.get_job(session, tenant_id=user.tenant_id, job_id=run.export_job_id)
        status = job.status if job is not None else "unknown"
        result_url = None
        if job is not None and job.status == "done" and job.result_key:
            result_url = generate_presigned_get_url(s3, bucket=bucket, key=job.result_key)
        result.append(
            ReportRunStatus(
                id=run.id,
                status=status,
                resultUrl=result_url,
                error=job.error if job is not None else None,
                notifiedAt=run.notified_at.isoformat() if run.notified_at else None,
                createdAt=run.created_at.isoformat(),
            )
        )
    return result
