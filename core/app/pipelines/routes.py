# SPDX-License-Identifier: Apache-2.0
"""Routes REST du Pipeline (SP-15a) — montées uniquement quand
CORE_ETL_ENABLED est actif (app.main, à la construction de l'app, jamais
par requête : cf. design §3.2 et ce plan, Global Constraints)."""
import os
from collections.abc import Callable

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.audit.writer import write_audit
from app.auth.dependency import get_current_user
from app.configs import repository as configs_repo
from app.db import get_session
from app.items import repository as items_repo
from app.pipelines import repository as pipelines_repo
from app.pipelines.jobs import run_pipeline_task
from app.pipelines.ops.schemas import ops_catalog
from app.pipelines.runtime import PipelineRuntimeError, preview_pipeline
from app.sharing.authorization import can
from app.users.models import User

router = APIRouter()


class RunResponse(BaseModel):
    runId: str


class RunStatus(BaseModel):
    id: str
    status: str
    startedAt: str | None
    finishedAt: str | None
    error: str | None
    nodeStats: dict


def _require_pipeline_access(session: Session, *, user: User, item_id: str, action: str) -> None:
    facts = items_repo.get_access_facts(session, tenant_id=user.tenant_id, item_id=item_id)
    if facts is None or not can(session, user_id=user.id, action="read", item=facts):
        raise HTTPException(status_code=404, detail="pipeline not found")
    if action != "read" and not can(session, user_id=user.id, action=action, item=facts):
        raise HTTPException(status_code=403, detail="not allowed")


def _require_pipeline_config(session: Session, item_id: str):
    config = configs_repo.get_config_by_item(session, item_id)
    if config is None or config.config.kind != "pipeline":
        raise HTTPException(status_code=404, detail="pipeline not found")
    return config


def get_task_deferrer() -> Callable[[str, str], None]:  # overridden in tests
    def deferrer(run_id: str, tenant_id: str) -> None:
        run_pipeline_task.defer(run_id=run_id, tenant_id=tenant_id)
    return deferrer


@router.get("/pipelines/ops")
def get_pipeline_ops() -> dict:
    return ops_catalog()


@router.post("/pipelines/{item_id}/run", response_model=RunResponse, status_code=202)
def run_pipeline_route(
    item_id: str,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
    defer_task: Callable[[str, str], None] = Depends(get_task_deferrer),
) -> RunResponse:
    _require_pipeline_access(session, user=user, item_id=item_id, action="write")
    _require_pipeline_config(session, item_id)
    run = pipelines_repo.create_run(session, tenant_id=user.tenant_id, pipeline_item_id=item_id)
    write_audit(
        session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="user",
        action="pipeline.run", object_type="pipeline_run", object_id=run.id,
        payload={"pipelineItemId": item_id},
    )
    # Commit avant de déférer : même raison que ingestion/routes.py
    # (create_upload_job) — un worker pourrait ramasser la tâche avant que
    # la ligne pipeline_runs ne soit visible autrement.
    session.commit()
    defer_task(run.id, user.tenant_id)
    return RunResponse(runId=run.id)


@router.get("/pipelines/{item_id}/runs", response_model=list[RunStatus])
def list_pipeline_runs(
    item_id: str,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> list[RunStatus]:
    _require_pipeline_access(session, user=user, item_id=item_id, action="read")
    _require_pipeline_config(session, item_id)
    runs = pipelines_repo.list_runs(session, tenant_id=user.tenant_id, pipeline_item_id=item_id)
    return [
        RunStatus(
            id=r.id, status=r.status,
            startedAt=r.started_at.isoformat() if r.started_at else None,
            finishedAt=r.finished_at.isoformat() if r.finished_at else None,
            error=r.error, nodeStats=r.node_stats,
        )
        for r in runs
    ]


@router.post("/pipelines/{item_id}/preview")
def preview_pipeline_route(
    item_id: str,
    upTo: str = Query(...),
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> list[dict]:
    _require_pipeline_access(session, user=user, item_id=item_id, action="read")
    config = _require_pipeline_config(session, item_id)
    try:
        return preview_pipeline(
            session=session, payload=config.config.pipeline, tenant_id=user.tenant_id, user=user,
            up_to=upTo, endpoint_url=os.environ.get("S3_ENDPOINT_URL", ""),
            access_key=os.environ.get("S3_ACCESS_KEY", ""), secret_key=os.environ.get("S3_SECRET_KEY", ""),
            base_uri=f"s3://{os.environ.get('S3_CDC_BUCKET', 'geostudio-cdc')}/cdc",
        )
    except PipelineRuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
