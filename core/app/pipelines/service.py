# SPDX-License-Identifier: Apache-2.0
"""Couche de service pour l'exécution d'un Pipeline — extraite de
POST /pipelines/{id}/run (app/pipelines/routes.py::run_pipeline_route) pour
être appelée à la fois par la route REST et par le tool MCP run_pipeline
(app/mcp/tools/pipelines.py) — SP-43 Étape 8. `actor_kind` distingue
seulement l'auteur de la ligne d'audit "pipeline.run" ("user" pour la route
REST, "agent" pour le tool MCP) — écart de design volontaire, documenté et
vérifié par tests/test_mcp_rest_parity.py, jamais à unifier sans décision
produit explicite."""

import hashlib
import secrets as py_secrets
from collections.abc import Callable

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.audit.writer import write_audit
from app.configs import repository as configs_repo
from app.configs.pipeline_params import PipelineParamError, resolve_params
from app.configs.repository import ConfigRead
from app.items import repository as items_repo
from app.jobs.common import resolve_owner_user
from app.jobs.defer import defer_resilient
from app.pipelines import repository as pipelines_repo
from app.pipelines.jobs import run_pipeline_task
from app.pipelines.models import PipelineWebhookToken
from app.roles.guards import require_privilege
from app.roles.kind_registry import privilege_for_kind
from app.roles.privileges import Privilege
from app.sharing.authorization import can
from app.users.models import User


def require_pipeline_access(session: Session, *, user: User, item_id: str, action: str) -> None:
    facts = items_repo.get_access_facts(session, tenant_id=user.tenant_id, item_id=item_id)
    if facts is None or not can(session, user_id=user.id, action="read", item=facts):
        raise HTTPException(status_code=404, detail="pipeline not found")
    if action != "read" and not can(session, user_id=user.id, action=action, item=facts):
        raise HTTPException(status_code=403, detail="not allowed")


def require_pipeline_config(session: Session, item_id: str) -> ConfigRead:
    config = configs_repo.get_config_by_item(session, item_id)
    if config is None or config.config.kind != "pipeline":
        raise HTTPException(status_code=404, detail="pipeline not found")
    return config


def pipeline_writes_dataset(config: ConfigRead) -> bool:
    """SP-42, revue des lots de correctifs 2/3bis (point 2, Important) : un
    nœud writer.dataset crée (app.pipelines.runtime::run_pipeline, branche
    else) ou mute (même fonction, branche p.datasetId is not None) une
    config kind="dataset" — mappée sur data.manage
    (app.roles.kind_registry::privilege_for_kind) — sans jamais consulter ce
    privilège sur l'appelant de /run : seul `write` sur l'item pipeline
    était exigé. Réutilisé par le tool MCP run_pipeline, même mapping."""
    payload = config.config.pipeline
    assert payload is not None  # garanti par config.config.kind == "pipeline"
    return any(node.op == "writer.dataset" for node in payload.nodes)


def require_data_manage_if_pipeline_writes_dataset(
    session: Session, user: User, config: ConfigRead
) -> None:
    # SP-43 Étape 1 : consulte le même registre que les autres sites
    # (app.configs.routes, app.mcp.tools, app.tileset3d/terrain3d.routes) au
    # lieu de recopier Privilege.DATA_MANAGE.value en dur.
    if pipeline_writes_dataset(config):
        require_privilege(session, user, privilege_for_kind("dataset"))


def default_task_deferrer() -> Callable[[str, str], None]:
    def deferrer(run_id: str, tenant_id: str) -> None:
        run_pipeline_task.defer(run_id=run_id, tenant_id=tenant_id)

    return deferrer


def _defer_or_fail(
    session: Session, run_id: str, tenant_id: str, defer_task: Callable[[str, str], None]
) -> None:
    """AUD-025 : un échec définitif de mise en file marque le run `failed` tout de
    suite (sinon il resterait `pending` et bloquerait tout nouveau run en 409)."""
    try:
        defer_resilient(lambda: defer_task(run_id, tenant_id))
    except HTTPException:
        pipelines_repo.mark_failed(
            session, run_id=run_id, error="mise en file impossible : file de jobs indisponible"
        )
        session.commit()
        raise


def run_pipeline_service(
    session: Session,
    *,
    user: User,
    item_id: str,
    defer_task: Callable[[str, str], None],
    actor_kind: str = "user",
    params: dict | None = None,
) -> str:
    """Extrait de app/pipelines/routes.py::run_pipeline_route — même
    séquence de gardes, identique pour la route REST et pour le tool MCP
    run_pipeline. Retourne le run_id ; `actor_kind` distingue seulement
    l'auteur de l'audit (cf. docstring du module)."""
    require_pipeline_access(session, user=user, item_id=item_id, action="write")
    config = require_pipeline_config(session, item_id)
    require_data_manage_if_pipeline_writes_dataset(session, user, config)
    payload = config.config.pipeline
    assert payload is not None
    try:
        values = resolve_params(payload.parameters, params)
    except PipelineParamError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    try:
        run = pipelines_repo.create_run_unless_active(
            session, tenant_id=user.tenant_id, pipeline_item_id=item_id, params=values
        )
    except pipelines_repo.PipelineRunActive:
        # REV-310 : REST, MCP (HTTPException -> ValueError) et webhook partagent ce garde.
        raise HTTPException(
            status_code=409,
            detail="Une exécution de ce pipeline est déjà en cours ou en file d'attente.",
        ) from None
    write_audit(
        session,
        tenant_id=user.tenant_id,
        actor_id=user.id,
        actor_kind=actor_kind,
        action="pipeline.run",
        object_type="pipeline_run",
        object_id=run.id,
        payload={"pipelineItemId": item_id, **({"params": values} if values else {})},
    )
    # Commit avant de déférer : même raison que ingestion/routes.py
    # (create_upload_job) — un worker pourrait ramasser la tâche avant que
    # la ligne pipeline_runs ne soit visible autrement.
    session.commit()
    _defer_or_fail(session, run.id, user.tenant_id, defer_task)
    return run.id


def retry_pipeline_run_service(
    session: Session,
    *,
    user: User,
    run_id: str,
    defer_task: Callable[[str, str], None],
    from_start: bool = False,
) -> str:
    """F5 : relance un run `failed` dans un NOUVEAU run (l'historique garde
    l'échec). Par défaut REPREND : les nœuds réussis ne sont pas rejoués (points
    de reprise du run racine) ; `from_start=True` rejoue tout. Mêmes gardes que
    run_pipeline_service ; `create_run_unless_active` fait office de verrou
    (une 2e reprise concurrente reçoit 409)."""
    run = pipelines_repo.get_run(session, tenant_id=user.tenant_id, run_id=run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    item_id = run.pipeline_item_id
    require_pipeline_access(session, user=user, item_id=item_id, action="write")
    config = require_pipeline_config(session, item_id)
    require_data_manage_if_pipeline_writes_dataset(session, user, config)
    if run.status != "failed":
        raise HTTPException(
            status_code=409, detail=f"run is {run.status}, only a failed run can be retried"
        )
    appenders = config.config.pipeline.append_writers() if config.config.pipeline else []
    if appenders:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Reprise/rejeu refusé : le writer {', '.join(appenders)} n'est pas idempotent "
                "(mode 'append' : dupliquerait des lignes déjà écrites, utilisez 'upsert' ou "
                "'replace' ; writer de messagerie : renverrait les messages déjà partis). "
                "Relancez une exécution complète."
            ),
        )
    # Les writers sont toujours rejoués (C1) : leurs stats de l'échec ne sont pas reprises.
    nodes = config.config.pipeline.nodes if config.config.pipeline else []
    writer_ids = {n.id for n in nodes if n.kind == "writer"}
    try:
        new_run = pipelines_repo.create_run_unless_active(
            session,
            tenant_id=user.tenant_id,
            pipeline_item_id=item_id,
            params=run.params,
            resume_of=None if from_start else (run.resume_of or run.id),
            node_stats=None
            if from_start
            else {k: v for k, v in (run.node_stats or {}).items() if k not in writer_ids},
        )
    except pipelines_repo.PipelineRunActive:
        raise HTTPException(
            status_code=409,
            detail="Une exécution de ce pipeline est déjà en cours ou en file d'attente.",
        ) from None
    write_audit(
        session,
        tenant_id=user.tenant_id,
        actor_id=user.id,
        actor_kind="user",
        action="pipeline.run.retry",
        object_type="pipeline_run",
        object_id=new_run.id,
        payload={"pipelineItemId": item_id, "retryOf": run.id, "fromStart": from_start},
    )
    session.commit()  # avant defer : le worker doit voir la ligne
    _defer_or_fail(session, new_run.id, user.tenant_id, defer_task)
    return new_run.id


# --- Déclenchement de pipeline par webhook entrant (GAP-24, SP-53) ---


def _hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode()).hexdigest()


def create_webhook_token_service(
    session: Session, *, user: User, item_id: str
) -> tuple[PipelineWebhookToken, str]:
    """Génère un jeton de déclenchement — retourne le jeton en clair une
    seule fois, jamais recalculable ni relisible ensuite (seul le hash est
    persisté). Exige write sur le pipeline ET
    Privilege.AUTOMATION_SECRETS_MANAGE (un jeton de déclenchement est un
    secret d'automatisation par nature — referme un des deux privilèges
    orphelins de REV-097 en sous-produit de cette tâche)."""
    require_pipeline_access(session, user=user, item_id=item_id, action="write")
    require_privilege(session, user, Privilege.AUTOMATION_SECRETS_MANAGE.value)
    raw_token = py_secrets.token_urlsafe(32)
    token = pipelines_repo.create_webhook_token(
        session,
        tenant_id=user.tenant_id,
        pipeline_item_id=item_id,
        token_hash=_hash_token(raw_token),
        created_by=user.id,
    )
    write_audit(
        session,
        tenant_id=user.tenant_id,
        actor_id=user.id,
        actor_kind="user",
        action="pipeline.webhook_token.create",
        object_type="pipeline_webhook_token",
        object_id=token.id,
        payload={"pipelineItemId": item_id},
    )
    session.commit()
    return token, raw_token


def revoke_webhook_token_service(
    session: Session, *, user: User, item_id: str, token_id: str
) -> None:
    require_pipeline_access(session, user=user, item_id=item_id, action="write")
    token = pipelines_repo.get_webhook_token(session, tenant_id=user.tenant_id, token_id=token_id)
    if token is None or token.pipeline_item_id != item_id:
        raise HTTPException(status_code=404, detail="webhook token not found")
    pipelines_repo.delete_webhook_token(session, token)
    write_audit(
        session,
        tenant_id=user.tenant_id,
        actor_id=user.id,
        actor_kind="user",
        action="pipeline.webhook_token.delete",
        object_type="pipeline_webhook_token",
        object_id=token_id,
        payload={"pipelineItemId": item_id},
    )
    session.commit()


def trigger_pipeline_by_webhook_service(
    session: Session,
    *,
    item_id: str,
    raw_token: str,
    defer_task: Callable[[str, str], None],
    params: dict | None = None,
) -> str:
    """Seul point d'entrée du déclenchement webhook — réutilise
    run_pipeline_service tel quel (mêmes gardes que REST/MCP), seul
    actor_kind="webhook" diffère. Ne JAMAIS dupliquer create_run+defer ici
    (spec SP-53 §6.1) : le balayage cron (run_pipeline_sweep_task) est déjà
    la 2e implémentation de cette séquence, pas une 3e à créer."""
    token = pipelines_repo.get_webhook_token_by_hash(session, token_hash=_hash_token(raw_token))
    if token is None or token.pipeline_item_id != item_id:
        # 404 dans les deux cas (jeton inconnu OU jeton valide pour un autre
        # pipeline) : ne jamais révéler si le jeton existe mais pour un
        # autre pipeline (spec SP-53 §6.3).
        raise HTTPException(status_code=404, detail="pipeline not found")
    try:
        owner = resolve_owner_user(
            session, tenant_id=token.tenant_id, item_id=token.pipeline_item_id
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="pipeline not found") from exc
    run_id = run_pipeline_service(
        session,
        user=owner,
        item_id=token.pipeline_item_id,
        defer_task=defer_task,
        actor_kind="webhook",
        params=params,
    )
    # Best-effort, hors du chemin critique : un échec ici ne doit jamais
    # faire échouer un déclenchement par ailleurs réussi.
    try:
        pipelines_repo.touch_webhook_token(session, token)
        session.commit()
    except Exception:  # noqa: BLE001 — best-effort explicite, jamais remonté
        session.rollback()
    return run_id
