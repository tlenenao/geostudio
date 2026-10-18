# SPDX-License-Identifier: Apache-2.0
"""Rapports de qualité d'une collection (ARC-14) : déclenchement et lecture."""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.audit.writer import write_audit
from app.auth.dependency import get_current_user
from app.collections.repository import get_access_facts
from app.collections.routes import get_collection_for_read
from app.collections.sensitive import may_read_sensitive
from app.configs.geo_limits_dep import get_request_geo_limits
from app.db import get_session
from app.jobs.defer import defer_resilient
from app.quality import repository as repo
from app.quality.jobs import run_quality_check_task
from app.sharing.authorization import can
from app.sharing.geo_limits import refuse_if_geo_limited

router = APIRouter()


class QualityReportOut(BaseModel):
    id: str
    collectionId: str
    status: str
    checked: int
    summary: dict | None
    violations: list | None
    error: str | None
    createdAt: str
    finishedAt: str | None


def _out(r) -> QualityReportOut:
    return QualityReportOut(
        id=r.id,
        collectionId=r.collection_id,
        status=r.status,
        checked=r.checked,
        summary=r.summary,
        violations=r.violations,
        error=r.error,
        createdAt=r.created_at.isoformat(),
        finishedAt=r.finished_at.isoformat() if r.finished_at else None,
    )


@router.post("/collections/{collection_id}/quality-checks", status_code=202)
def start_quality_check(
    collection_id: str,
    user=Depends(get_current_user),
    session: Session = Depends(get_session, scope="function"),
    geo_limits=Depends(get_request_geo_limits),
) -> QualityReportOut:
    col = get_collection_for_read(session, user, collection_id)
    if not can(
        session,
        user_id=user.id,
        action="write",
        item=get_access_facts(col),
        kind="collection",
        actor_is_admin=user.acts_as_admin(),
    ):
        raise HTTPException(status_code=403, detail="write access required")
    refuse_if_geo_limited(geo_limits, col.table_name, path="quality check")
    if not any(r["kind"] in ("constraint", "batch") for r in col.attribute_rules):
        raise HTTPException(status_code=409, detail="collection has no constraint/batch rule")
    report = repo.create_report(
        session,
        tenant_id=col.tenant_id,
        collection_id=col.id,
        requested_by=user.id,
        masked=not may_read_sensitive(session, user, col),
    )
    write_audit(
        session,
        tenant_id=col.tenant_id,
        actor_id=user.id,
        actor_kind="user",
        action="collection.quality_check",
        object_type="quality_report",
        object_id=report.id,
        payload={"collectionId": col.id},
    )
    session.commit()  # visible avant le defer (piège n°14)
    # Rapport `pending` repris par sweep_quality_reports_task ; 503 propre sinon un 500.
    defer_resilient(
        lambda: run_quality_check_task.defer(report_id=report.id, tenant_id=col.tenant_id)
    )
    return _out(report)


@router.get("/collections/{collection_id}/quality-checks")
def list_quality_checks(
    collection_id: str,
    limit: int = Query(20, ge=1, le=100),
    user=Depends(get_current_user),
    session: Session = Depends(get_session, scope="function"),
    geo_limits=Depends(get_request_geo_limits),
) -> list[QualityReportOut]:
    col = get_collection_for_read(session, user, collection_id)
    # Fail-closed : un rapport couvre toute la collection, il n'est pas découpé.
    refuse_if_geo_limited(geo_limits, col.table_name, path="quality report")
    sees = may_read_sensitive(session, user, col)
    rows = repo.list_reports(session, tenant_id=col.tenant_id, collection_id=col.id, limit=limit)
    return [_out(r) for r in rows if sees or r.masked]


@router.get("/collections/{collection_id}/quality-checks/{report_id}")
def get_quality_check(
    collection_id: str,
    report_id: str,
    user=Depends(get_current_user),
    session: Session = Depends(get_session, scope="function"),
    geo_limits=Depends(get_request_geo_limits),
) -> QualityReportOut:
    col = get_collection_for_read(session, user, collection_id)
    refuse_if_geo_limited(geo_limits, col.table_name, path="quality report")
    report = repo.get_report(session, report_id, col.tenant_id)
    # Un rapport non masqué (règles sur champs sensibles) ne se lit pas par un lecteur masqué.
    if (
        report is None
        or report.collection_id != col.id
        or (not report.masked and not may_read_sensitive(session, user, col))
    ):
        raise HTTPException(status_code=404, detail="quality report not found")
    return _out(report)
