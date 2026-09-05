# SPDX-License-Identifier: Apache-2.0
"""Couche de service pour l'exécution d'un Pipeline — extraite de
POST /pipelines/{id}/run (app/pipelines/routes.py::run_pipeline_route) pour
être appelée à la fois par la route REST et par le tool MCP run_pipeline
(app/mcp/tools/pipelines.py) — SP-43 Étape 8. `actor_kind` distingue
seulement l'auteur de la ligne d'audit "pipeline.run" ("user" pour la route
REST, "agent" pour le tool MCP) — écart de design volontaire, documenté et
vérifié par tests/test_mcp_rest_parity.py, jamais à unifier sans décision
produit explicite."""

from collections.abc import Callable

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.audit.writer import write_audit
from app.configs import repository as configs_repo
from app.configs.repository import ConfigRead
from app.items import repository as items_repo
from app.pipelines import repository as pipelines_repo
from app.pipelines.jobs import run_pipeline_task
from app.roles.guards import require_privilege
from app.roles.kind_registry import privilege_for_kind
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


def run_pipeline_service(
    session: Session,
    *,
    user: User,
    item_id: str,
    defer_task: Callable[[str, str], None],
    actor_kind: str = "user",
) -> str:
    """Extrait de app/pipelines/routes.py::run_pipeline_route — même
    séquence de gardes, identique pour la route REST et pour le tool MCP
    run_pipeline. Retourne le run_id ; `actor_kind` distingue seulement
    l'auteur de l'audit (cf. docstring du module)."""
    require_pipeline_access(session, user=user, item_id=item_id, action="write")
    config = require_pipeline_config(session, item_id)
    require_data_manage_if_pipeline_writes_dataset(session, user, config)
    run = pipelines_repo.create_run(session, tenant_id=user.tenant_id, pipeline_item_id=item_id)
    write_audit(
        session,
        tenant_id=user.tenant_id,
        actor_id=user.id,
        actor_kind=actor_kind,
        action="pipeline.run",
        object_type="pipeline_run",
        object_id=run.id,
        payload={"pipelineItemId": item_id},
    )
    # Commit avant de déférer : même raison que ingestion/routes.py
    # (create_upload_job) — un worker pourrait ramasser la tâche avant que
    # la ligne pipeline_runs ne soit visible autrement.
    session.commit()
    defer_task(run.id, user.tenant_id)
    return run.id
