# SPDX-License-Identifier: Apache-2.0
"""Routes REST du Pipeline (SP-15a) — montées uniquement quand
CORE_ETL_ENABLED est actif (app.main, à la construction de l'app, jamais
par requête : cf. design §3.2 et ce plan, Global Constraints)."""

import os
from collections.abc import Callable

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.dependency import get_current_user
from app.db import get_session
from app.pipelines import repository as pipelines_repo
from app.pipelines.ops.qgis_algorithms import QGIS_ALGORITHMS
from app.pipelines.ops.schemas import ops_catalog
from app.pipelines.runtime import PipelineRuntimeError, preview_pipeline
from app.pipelines.service import (
    create_webhook_token_service,
    default_task_deferrer,
    require_pipeline_access,
    require_pipeline_config,
    revoke_webhook_token_service,
    run_pipeline_service,
    trigger_pipeline_by_webhook_service,
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


class WebhookTokenCreated(BaseModel):
    id: str
    token: str
    createdAt: str


class WebhookTokenSummary(BaseModel):
    id: str
    createdAt: str
    lastUsedAt: str | None


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


_RUNS_MAX_LIMIT = 1000


@router.get("/pipelines/{item_id}/runs", response_model=list[RunStatus])
def list_pipeline_runs(
    item_id: str,
    limit: int = Query(100, ge=1),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> list[RunStatus]:
    require_pipeline_access(session, user=user, item_id=item_id, action="read")
    require_pipeline_config(session, item_id)
    limit = min(limit, _RUNS_MAX_LIMIT)
    runs = pipelines_repo.list_runs(
        session, tenant_id=user.tenant_id, pipeline_item_id=item_id, limit=limit, offset=offset
    )
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


@router.post(
    "/pipelines/{item_id}/webhook-tokens", response_model=WebhookTokenCreated, status_code=201
)
def create_webhook_token_route(
    item_id: str,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> WebhookTokenCreated:
    token, raw = create_webhook_token_service(session, user=user, item_id=item_id)
    return WebhookTokenCreated(id=token.id, token=raw, createdAt=token.created_at.isoformat())


@router.get("/pipelines/{item_id}/webhook-tokens", response_model=list[WebhookTokenSummary])
def list_webhook_tokens_route(
    item_id: str,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> list[WebhookTokenSummary]:
    require_pipeline_access(session, user=user, item_id=item_id, action="read")
    rows = pipelines_repo.list_webhook_tokens_for_pipeline(
        session, tenant_id=user.tenant_id, pipeline_item_id=item_id
    )
    return [
        WebhookTokenSummary(
            id=r.id,
            createdAt=r.created_at.isoformat(),
            lastUsedAt=r.last_used_at.isoformat() if r.last_used_at else None,
        )
        for r in rows
    ]


@router.delete("/pipelines/{item_id}/webhook-tokens/{token_id}", status_code=204)
def delete_webhook_token_route(
    item_id: str,
    token_id: str,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> None:
    revoke_webhook_token_service(session, user=user, item_id=item_id, token_id=token_id)


@router.post("/pipelines/{item_id}/trigger", response_model=RunResponse, status_code=202)
def trigger_pipeline_webhook_route(
    item_id: str,
    authorization: str | None = Header(default=None),
    session: Session = Depends(get_session),
    defer_task: Callable[[str, str], None] = Depends(get_task_deferrer),
) -> RunResponse:
    """Seule route de tout le dépôt sans Depends(get_current_user) — un
    appelant externe (CI, capteur IoT) n'a pas de session OIDC : le secret
    bearer remplace entièrement l'authentification OIDC pour cette route
    précise. GAP-24, SP-53."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    raw_token = authorization.removeprefix("Bearer ")
    run_id = trigger_pipeline_by_webhook_service(
        session, item_id=item_id, raw_token=raw_token, defer_task=defer_task
    )
    return RunResponse(runId=run_id)
