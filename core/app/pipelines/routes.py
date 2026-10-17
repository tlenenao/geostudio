# SPDX-License-Identifier: Apache-2.0
"""Routes REST du Pipeline (SP-15a) — montées uniquement quand
CORE_ETL_ENABLED est actif (app.main, à la construction de l'app, jamais
par requête : cf. design §3.2 et ce plan, Global Constraints)."""

import os
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import croniter
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.audit.writer import write_audit
from app.auth.dependency import forbid_api_key, get_current_user
from app.configs.schemas import PipelinePayload
from app.db import get_session
from app.pipelines import repository as pipelines_repo
from app.pipelines.ops.contracts import ops_catalog
from app.pipelines.runtime import PipelineRuntimeError, preview_pipeline
from app.pipelines.service import (
    create_webhook_token_service,
    default_task_deferrer,
    require_pipeline_access,
    require_pipeline_config,
    retry_pipeline_run_service,
    revoke_webhook_token_service,
    run_pipeline_service,
    trigger_pipeline_by_webhook_service,
)
from app.users.models import User

router = APIRouter()


class RunResponse(BaseModel):
    runId: str


class RunRequest(BaseModel):
    """Corps optionnel de POST /pipelines/{id}/run et /trigger (ARC-K2/F3).

    Les `params` sont conservés EN CLAIR dans pipeline_runs et l'audit : n'y mettez
    jamais de secret (utilisez le coffre de secrets des connecteurs)."""

    params: dict[str, Any] = Field(default_factory=dict)


class RunStatus(BaseModel):
    id: str
    status: str
    startedAt: str | None
    finishedAt: str | None
    error: str | None
    nodeStats: dict
    params: dict | None = None
    attempt: int = 1
    nextRetryAt: str | None = None
    resumeOf: str | None = None
    # Des points de reprise existent encore : « Reprendre » évite de rejouer les nœuds réussis.
    resumable: bool = False


class WebhookTokenCreated(BaseModel):
    id: str
    token: str
    createdAt: str


class WebhookTokenSummary(BaseModel):
    id: str
    createdAt: str
    lastUsedAt: str | None


class PipelinePreviewRequest(BaseModel):
    pipeline: PipelinePayload | None = None
    # Valeurs de `{{param.x}}` pour l'aperçu (défauts déclarés sinon).
    params: dict[str, Any] | None = None


class NextRunResponse(BaseModel):
    nextRun: str


def get_task_deferrer() -> Callable[[str, str], None]:  # overridden in tests
    return default_task_deferrer()


@router.get("/pipelines/ops")
def get_pipeline_ops(user: User = Depends(get_current_user)) -> dict:
    return ops_catalog()


@router.get("/pipelines/next-run", response_model=NextRunResponse)
def get_pipeline_next_run(
    cron: str = Query(...),
    user: User = Depends(get_current_user),
) -> NextRunResponse:
    if len(cron.split()) != 5 or not croniter.croniter.is_valid(cron):
        raise HTTPException(status_code=400, detail=f"invalid cron expression: {cron!r}")
    try:
        next_tick = croniter.croniter(cron, datetime.now(UTC)).get_next(datetime)
    except croniter.CroniterBadDateError as exc:
        raise HTTPException(
            status_code=400, detail=f"cron expression has no future occurrence: {cron!r}"
        ) from exc
    return NextRunResponse(nextRun=next_tick.isoformat())


class RetryRequest(BaseModel):
    # True : rejoue tout depuis le début (« Rejouer ») ; False : reprend au nœud en échec.
    fromStart: bool = False


# Déclarée AVANT les routes à paramètre de chemin : /pipelines/runs/... ne doit pas
# être capturée par /pipelines/{item_id}/...
@router.post("/pipelines/runs/{run_id}/retry", response_model=RunResponse, status_code=202)
def retry_pipeline_run_route(
    run_id: str,
    body: RetryRequest | None = None,
    session: Session = Depends(get_session, scope="function"),
    user: User = Depends(get_current_user),
    defer_task: Callable[[str, str], None] = Depends(get_task_deferrer),
) -> RunResponse:
    new_id = retry_pipeline_run_service(
        session,
        user=user,
        run_id=run_id,
        defer_task=defer_task,
        from_start=bool(body and body.fromStart),
    )
    return RunResponse(runId=new_id)


@router.post("/pipelines/{item_id}/run", response_model=RunResponse, status_code=202)
def run_pipeline_route(
    item_id: str,
    body: RunRequest | None = None,
    session: Session = Depends(get_session, scope="function"),
    user: User = Depends(get_current_user),
    defer_task: Callable[[str, str], None] = Depends(get_task_deferrer),
) -> RunResponse:
    run_id = run_pipeline_service(
        session,
        user=user,
        item_id=item_id,
        defer_task=defer_task,
        params=body.params if body else None,
    )
    return RunResponse(runId=run_id)


def _run_status(r) -> RunStatus:
    return RunStatus(
        id=r.id,
        status=r.status,
        startedAt=r.started_at.isoformat() if r.started_at else None,
        finishedAt=r.finished_at.isoformat() if r.finished_at else None,
        error=r.error,
        nodeStats=r.node_stats,
        params=r.params,
        attempt=r.attempt,
        nextRetryAt=r.next_retry_at.isoformat() if r.next_retry_at else None,
        resumeOf=r.resume_of,
        resumable=r.status == "failed" and r.resumable,
    )


@router.post("/pipelines/{item_id}/runs/{run_id}/cancel", response_model=RunStatus)
def cancel_pipeline_run_route(
    item_id: str,
    run_id: str,
    session: Session = Depends(get_session, scope="function"),
    user: User = Depends(get_current_user),
) -> RunStatus:
    """t03b-009 : demande l'arrêt d'un run en file ou en cours (effectif entre
    deux lots d'écriture)."""
    require_pipeline_access(session, user=user, item_id=item_id, action="write")
    run = pipelines_repo.get_run(session, tenant_id=user.tenant_id, run_id=run_id)
    if run is None or run.pipeline_item_id != item_id:
        raise HTTPException(status_code=404, detail="run not found")
    if run.status in ("cancel_requested", "cancelled"):
        return _run_status(run)  # idempotent (REV-275 c) : déjà demandé, pas de nouvel audit
    if run.status not in ("queued", "running", "retrying"):
        raise HTTPException(status_code=409, detail=f"run is {run.status}, cannot be cancelled")
    if pipelines_repo.request_cancel(session, run) not in ("cancelled", "cancel_requested"):
        # Le run a fini entre la lecture et l'UPDATE conditionnel : rien annulé, pas d'audit.
        session.rollback()
        raise HTTPException(status_code=409, detail=f"run is {run.status}, cannot be cancelled")
    write_audit(
        session,
        tenant_id=user.tenant_id,
        actor_id=user.id,
        actor_kind="user",
        action="pipeline.run.cancel",
        object_type="pipeline_run",
        object_id=run.id,
        payload={"pipelineItemId": item_id},
    )
    session.commit()
    return _run_status(run)


_RUNS_MAX_LIMIT = 1000


@router.get("/pipelines/{item_id}/runs", response_model=list[RunStatus])
def list_pipeline_runs(
    item_id: str,
    limit: int = Query(100, ge=1),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_session, scope="function"),
    user: User = Depends(get_current_user),
) -> list[RunStatus]:
    require_pipeline_access(session, user=user, item_id=item_id, action="read")
    require_pipeline_config(session, item_id)
    limit = min(limit, _RUNS_MAX_LIMIT)
    runs = pipelines_repo.list_runs(
        session, tenant_id=user.tenant_id, pipeline_item_id=item_id, limit=limit, offset=offset
    )
    return [_run_status(r) for r in runs]


class ReaderStateEntry(BaseModel):
    nodeId: str
    cursor: str


@router.get("/pipelines/{item_id}/reader-state", response_model=list[ReaderStateEntry])
def get_reader_state_route(
    item_id: str,
    session: Session = Depends(get_session, scope="function"),
    user: User = Depends(get_current_user),
) -> list[ReaderStateEntry]:
    """Curseurs de lecture incrémentale par nœud reader (ARC-K2/F4)."""
    require_pipeline_access(session, user=user, item_id=item_id, action="read")
    states = pipelines_repo.get_reader_states(
        session, tenant_id=user.tenant_id, pipeline_item_id=item_id
    )
    return [ReaderStateEntry(nodeId=n, cursor=c) for n, c in sorted(states.items())]


@router.delete("/pipelines/{item_id}/reader-state", status_code=204)
def reset_reader_state_route(
    item_id: str,
    nodeId: str | None = Query(None),
    session: Session = Depends(get_session, scope="function"),
    user: User = Depends(get_current_user),
) -> None:
    """Réinitialise le curseur (un nœud, ou tous) : le prochain run relit tout."""
    require_pipeline_access(session, user=user, item_id=item_id, action="write")
    removed = pipelines_repo.delete_reader_states(
        session, tenant_id=user.tenant_id, pipeline_item_id=item_id, node_id=nodeId
    )
    write_audit(
        session,
        tenant_id=user.tenant_id,
        actor_id=user.id,
        actor_kind="user",
        action="pipeline.reader_state.reset",
        object_type="pipeline",
        object_id=item_id,
        payload={"nodeId": nodeId, "removed": removed},
    )
    session.commit()


@router.post("/pipelines/{item_id}/preview")
def preview_pipeline_route(
    item_id: str,
    upTo: str = Query(...),
    body: PipelinePreviewRequest | None = None,
    session: Session = Depends(get_session, scope="function"),
    user: User = Depends(get_current_user),
) -> list[dict]:
    require_pipeline_access(session, user=user, item_id=item_id, action="write")
    config = require_pipeline_config(session, item_id)
    payload = body.pipeline if body and body.pipeline is not None else config.config.pipeline
    try:
        return preview_pipeline(
            session=session,
            payload=payload,
            tenant_id=user.tenant_id,
            user=user,
            up_to=upTo,
            endpoint_url=os.environ.get("S3_ENDPOINT_URL", ""),
            access_key=os.environ.get("S3_ACCESS_KEY", ""),
            secret_key=os.environ.get("S3_SECRET_KEY", ""),
            base_uri=f"s3://{os.environ.get('S3_CDC_BUCKET', 'geostudio-cdc')}/cdc",
            params=body.params if body else None,
        )
    except PipelineRuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/pipelines/{item_id}/webhook-tokens",
    response_model=WebhookTokenCreated,
    status_code=201,
    dependencies=[Depends(forbid_api_key)],  # AUD-094 : session interactive seulement
)
def create_webhook_token_route(
    item_id: str,
    session: Session = Depends(get_session, scope="function"),
    user: User = Depends(get_current_user),
) -> WebhookTokenCreated:
    token, raw = create_webhook_token_service(session, user=user, item_id=item_id)
    return WebhookTokenCreated(id=token.id, token=raw, createdAt=token.created_at.isoformat())


@router.get("/pipelines/{item_id}/webhook-tokens", response_model=list[WebhookTokenSummary])
def list_webhook_tokens_route(
    item_id: str,
    session: Session = Depends(get_session, scope="function"),
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
    session: Session = Depends(get_session, scope="function"),
    user: User = Depends(get_current_user),
) -> None:
    revoke_webhook_token_service(session, user=user, item_id=item_id, token_id=token_id)


@router.post("/pipelines/{item_id}/trigger", response_model=RunResponse, status_code=202)
def trigger_pipeline_webhook_route(
    item_id: str,
    body: RunRequest | None = None,
    authorization: str | None = Header(default=None),
    session: Session = Depends(get_session, scope="function"),
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
        session,
        item_id=item_id,
        raw_token=raw_token,
        defer_task=defer_task,
        params=body.params if body else None,
    )
    return RunResponse(runId=run_id)
