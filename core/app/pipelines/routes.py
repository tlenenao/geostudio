# SPDX-License-Identifier: Apache-2.0
"""Routes REST du Pipeline (SP-15a) — montées uniquement quand
CORE_ETL_ENABLED est actif (app.main, à la construction de l'app, jamais
par requête : cf. design §3.2 et ce plan, Global Constraints)."""

import os
from collections.abc import Callable

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.dependency import get_current_user
from app.db import get_session
from app.pipelines import repository as pipelines_repo
from app.pipelines.ops.qgis_algorithms import QGIS_ALGORITHMS
from app.pipelines.ops.schemas import ops_catalog
from app.pipelines.runtime import PipelineRuntimeError, preview_pipeline
from app.pipelines.service import (
    default_task_deferrer,
    require_pipeline_access,
    require_pipeline_config,
    run_pipeline_service,
)
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


def get_task_deferrer() -> Callable[[str, str], None]:  # overridden in tests
    return default_task_deferrer()


@router.get("/pipelines/ops")
def get_pipeline_ops() -> dict:
    return ops_catalog()


@router.get("/pipelines/ops/qgis-algorithms")
def get_qgis_algorithms() -> dict:
    return QGIS_ALGORITHMS


@router.post("/pipelines/{item_id}/run", response_model=RunResponse, status_code=202)
def run_pipeline_route(
    item_id: str,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
    defer_task: Callable[[str, str], None] = Depends(get_task_deferrer),
) -> RunResponse:
    run_id = run_pipeline_service(session, user=user, item_id=item_id, defer_task=defer_task)
    return RunResponse(runId=run_id)


@router.get("/pipelines/{item_id}/runs", response_model=list[RunStatus])
def list_pipeline_runs(
    item_id: str,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> list[RunStatus]:
    require_pipeline_access(session, user=user, item_id=item_id, action="read")
    require_pipeline_config(session, item_id)
    runs = pipelines_repo.list_runs(session, tenant_id=user.tenant_id, pipeline_item_id=item_id)
    return [
        RunStatus(
            id=r.id,
            status=r.status,
            startedAt=r.started_at.isoformat() if r.started_at else None,
            finishedAt=r.finished_at.isoformat() if r.finished_at else None,
            error=r.error,
            nodeStats=r.node_stats,
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
    require_pipeline_access(session, user=user, item_id=item_id, action="read")
    config = require_pipeline_config(session, item_id)
    try:
        return preview_pipeline(
            session=session,
            payload=config.config.pipeline,
            tenant_id=user.tenant_id,
            user=user,
            up_to=upTo,
            endpoint_url=os.environ.get("S3_ENDPOINT_URL", ""),
            access_key=os.environ.get("S3_ACCESS_KEY", ""),
            secret_key=os.environ.get("S3_SECRET_KEY", ""),
            base_uri=f"s3://{os.environ.get('S3_CDC_BUCKET', 'geostudio-cdc')}/cdc",
            qgis_worker_url=os.environ.get("QGIS_WORKER_URL", ""),
            qgis_worker_timeout_seconds=int(os.environ.get("QGIS_WORKER_TIMEOUT_SECONDS", "600")),
        )
    except PipelineRuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
