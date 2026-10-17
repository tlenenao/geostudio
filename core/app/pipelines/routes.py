# SPDX-License-Identifier: Apache-2.0
"""Routes REST du Pipeline (SP-15a) — montées uniquement quand
CORE_ETL_ENABLED est actif (app.main, à la construction de l'app, jamais
par requête : cf. design §3.2 et ce plan, Global Constraints)."""

import os
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import croniter
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.analytics.sql_sandbox import SqlSandboxError
from app.audit.writer import write_audit
from app.auth.dependency import forbid_api_key, get_current_user
from app.collections.introspection import Introspector
from app.collections.provisioning import create_empty_collection
from app.collections.routes import get_ddl_applier, get_introspector
from app.collections.schemas import EmptyCollectionColumn
from app.configs.schemas import PipelinePayload
from app.db import get_session
from app.pipelines import repository as pipelines_repo
from app.pipelines.ops.contracts import ops_catalog
from app.pipelines.runtime import (
    PipelineRuntimeError,
    describe_pipeline_output,
    preview_pipeline,
)
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
from app.roles.guards import require_privilege
from app.roles.kind_registry import privilege_for_kind
from app.roles.privileges import Privilege
from app.users.models import User

router = APIRouter()


def iso_utc(dt: datetime | None) -> str | None:
    """AUD-088 F11 : les colonnes sont des DateTime naïfs en UTC ; sans suffixe, le
    navigateur les lit en heure locale (décalage d'1-2 h affiché)."""
    if dt is None:
        return None
    return (dt if dt.tzinfo else dt.replace(tzinfo=UTC)).isoformat()


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
    # AUD-087 : nœud fautif d'un run en échec, quand il est connu.
    failedNodeId: str | None = None


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
    # Revue L5 I7 : coupe-circuit ouvert (3 échecs consécutifs) — seulement si `itemId`.
    scheduleSuspended: bool = False


def get_task_deferrer() -> Callable[[str, str], None]:  # overridden in tests
    return default_task_deferrer()


@router.get("/pipelines/ops")
def get_pipeline_ops(user: User = Depends(get_current_user)) -> dict:
    return ops_catalog()


@router.get("/pipelines/next-run", response_model=NextRunResponse)
def get_pipeline_next_run(
    cron: str = Query(...),
    tz: str = Query("UTC", max_length=64),
    itemId: str | None = Query(None),
    session: Session = Depends(get_session, scope="function"),
    user: User = Depends(get_current_user),
) -> NextRunResponse:
    suspended = False
    if itemId is not None:
        require_pipeline_access(session, user=user, item_id=itemId, action="read")
        suspended = pipelines_repo.schedule_suspended(session, item_id=itemId)
    if len(cron.split()) != 5 or not croniter.croniter.is_valid(cron):
        raise HTTPException(status_code=400, detail=f"invalid cron expression: {cron!r}")
    try:
        zone = ZoneInfo(tz)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"fuseau horaire inconnu : {tz!r}") from exc
    try:
        next_tick = croniter.croniter(cron, datetime.now(zone)).get_next(datetime)
    except croniter.CroniterBadDateError as exc:
        raise HTTPException(
            status_code=400, detail=f"cron expression has no future occurrence: {cron!r}"
        ) from exc
    return NextRunResponse(nextRun=next_tick.isoformat(), scheduleSuspended=suspended)


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
        startedAt=iso_utc(r.started_at),
        finishedAt=iso_utc(r.finished_at),
        error=r.error,
        nodeStats=r.node_stats,
        params=r.params,
        attempt=r.attempt,
        nextRetryAt=iso_utc(r.next_retry_at),
        resumeOf=r.resume_of,
        resumable=r.status == "failed" and r.resumable,
        failedNodeId=r.failed_node_id,
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


def _preview_kwargs(session: Session, user: User) -> dict[str, Any]:
    return {
        "session": session,
        "tenant_id": user.tenant_id,
        "user": user,
        "endpoint_url": os.environ.get("S3_ENDPOINT_URL", ""),
        "access_key": os.environ.get("S3_ACCESS_KEY", ""),
        "secret_key": os.environ.get("S3_SECRET_KEY", ""),
        "base_uri": f"s3://{os.environ.get('S3_CDC_BUCKET', 'geostudio-cdc')}/cdc",
    }


def _run_preview(
    session: Session, user: User, payload: PipelinePayload, up_to: str, params: dict | None
) -> list[dict]:
    try:
        return preview_pipeline(
            **_preview_kwargs(session, user), payload=payload, up_to=up_to, params=params
        )
    # AUD-087 : une expression refusée par le bac à sable ou un paramètre invalide est un
    # refus métier (400), jamais un 500.
    except (PipelineRuntimeError, SqlSandboxError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


_DUCKDB_TO_SQL = {
    "VARCHAR": "text",
    "BOOLEAN": "boolean",
    "TINYINT": "integer",
    "SMALLINT": "integer",
    "INTEGER": "integer",
    "BIGINT": "bigint",
    "HUGEINT": "bigint",
    "FLOAT": "double precision",
    "DOUBLE": "double precision",
    "DATE": "date",
    "TIMESTAMP": "timestamptz",
    "TIMESTAMP WITH TIME ZONE": "timestamptz",
}
_GEOM_MULTI = {
    "POINT": "MultiPoint",
    "MULTIPOINT": "MultiPoint",
    "LINESTRING": "MultiLineString",
    "MULTILINESTRING": "MultiLineString",
    "POLYGON": "MultiPolygon",
    "MULTIPOLYGON": "MultiPolygon",
}
# Colonnes posées par create_empty_collection elle-même (ou la géométrie, portée à part).
_RESERVED_TARGET_COLUMNS = {"geometry", "id", "tenant_id", "geom"}


class TargetCollectionRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    pipeline: PipelinePayload
    writerNodeId: str


class TargetCollectionCreated(BaseModel):
    collectionId: str


# Déclarée AVANT les routes /pipelines/{item_id}/… (même raison que /pipelines/preview).
@router.post(
    "/pipelines/target-collection", response_model=TargetCollectionCreated, status_code=201
)
def create_pipeline_target_collection_route(
    body: TargetCollectionRequest,
    session: Session = Depends(get_session, scope="function"),
    user: User = Depends(get_current_user),
    introspect: Introspector = Depends(get_introspector),
    apply_ddl: Callable = Depends(get_ddl_applier),
) -> TargetCollectionCreated:
    """AUD-088 F2 : crée une collection vide au schéma du flux qui alimente un writer."""
    require_privilege(session, user, privilege_for_kind("pipeline"))
    # Même porte que POST /collections/empty (DDL).
    require_privilege(session, user, Privilege.DATA_MANAGE.value)
    pred = next((e.from_ for e in body.pipeline.edges if e.to == body.writerNodeId), None)
    if pred is None:
        raise HTTPException(status_code=400, detail="le writer n'a pas d'entrée")
    try:
        schema = describe_pipeline_output(
            **_preview_kwargs(session, user), payload=body.pipeline, up_to=pred
        )
    except (PipelineRuntimeError, SqlSandboxError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    kinds = {_GEOM_MULTI.get(t) for t in schema.geometry_types}
    if None in kinds or len(kinds) > 1:
        raise HTTPException(
            status_code=400,
            detail=f"géométries hétérogènes en sortie ({', '.join(schema.geometry_types)}) : "
            "filtrer par type avant d'écrire",
        )
    if not kinds and any(n == "geometry" for n, _ in schema.columns):
        raise HTTPException(
            status_code=400,
            detail="type de géométrie indéterminé : le flux ne produit aucune géométrie non nulle",
        )
    try:
        columns = [
            EmptyCollectionColumn(name=n, sqlType=_DUCKDB_TO_SQL.get(t.split("(")[0], "text"))
            for n, t in schema.columns
            if n not in _RESERVED_TARGET_COLUMNS
        ]
    except ValueError as exc:  # nom de colonne trop long ou réservé
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    geometry_type = kinds.pop() if kinds else None
    target = create_empty_collection(
        session,
        tenant_id=user.tenant_id,
        owner_id=user.id,
        title=body.title,
        columns=columns,
        geometry_type=geometry_type,  # type: ignore[arg-type]
        srid=schema.srid if geometry_type else None,
        introspect=introspect,
        apply_ddl=apply_ddl,
    )
    return TargetCollectionCreated(collectionId=target.id)


class PipelineDraftPreviewRequest(BaseModel):
    pipeline: PipelinePayload
    params: dict[str, Any] | None = None


# Déclarée AVANT /pipelines/{item_id}/preview (sinon « preview » serait pris pour un item_id).
@router.post("/pipelines/preview")
def preview_unsaved_pipeline_route(
    body: PipelineDraftPreviewRequest,
    upTo: str = Query(...),
    session: Session = Depends(get_session, scope="function"),
    user: User = Depends(get_current_user),
) -> list[dict]:
    """AUD-009 : aperçu d'un pipeline jamais enregistré (pas encore d'item). Même porte que
    la création d'un pipeline ; les lectures restent soumises à can() nœud par nœud."""
    require_privilege(session, user, privilege_for_kind("pipeline"))
    return _run_preview(session, user, body.pipeline, upTo, body.params)


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
    assert payload is not None
    return _run_preview(session, user, payload, upTo, body.params if body else None)


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
    return WebhookTokenCreated(id=token.id, token=raw, createdAt=iso_utc(token.created_at) or "")


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
            createdAt=iso_utc(r.created_at) or "",
            lastUsedAt=iso_utc(r.last_used_at),
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
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", max_length=128),
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
        idempotency_key=idempotency_key,
    )
    return RunResponse(runId=run_id)
