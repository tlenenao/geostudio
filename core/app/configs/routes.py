# SPDX-License-Identifier: Apache-2.0
from fastapi import APIRouter, Depends, HTTPException, Response, status
from opentelemetry import metrics
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.audit.writer import write_audit
from app.auth.dependency import get_current_user, is_etl_enabled, is_export_enabled
from app.configs import repository as repo
from app.configs.alert_validation import validate_alert_payload as _validate_alert_payload
from app.configs.bookmark_validation import validate_bookmark_payload as _validate_bookmark_payload
from app.configs.dataset_validation import validate_dataset_payload as _validate_dataset_payload
from app.configs.extension_permissions import (
    ExtensionPermissionError,
    validate_extension_permissions,
)
from app.configs.pipeline_validation import validate_pipeline_payload as _validate_pipeline_payload
from app.configs.report_validation import validate_report_payload as _validate_report_payload
from app.configs.repository import ConfigRead, RevisionInfo
from app.configs.schemas import BuilderConfig
from app.configs.terrain3d_validation import (
    validate_terrain3d_payload as _validate_terrain3d_payload,
)
from app.configs.tileset3d_validation import (
    validate_tileset3d_payload as _validate_tileset3d_payload,
)
from app.db import get_session
from app.items import repository as items_repo
from app.items.models import Item
from app.items.slug import InvalidSlugError, SlugCollisionError
from app.roles.guards import require_privilege
from app.roles.kind_registry import privilege_for_kind
from app.sharing.authorization import can
from app.users.models import User

router = APIRouter()

_meter = metrics.get_meter(__name__)
_apps_runtime_executions_counter = _meter.create_counter(
    "geostudio.apps.runtime_executions",
    unit="1",
    description="GET config calls with mode=runtime",
)


class CreateConfigRequest(BaseModel):
    title: str
    config: BuilderConfig
    slug: str | None = None


class RollbackRequest(BaseModel):
    version: int


def _require_access(session: Session, *, user: User, item_id: str, action: str) -> None:
    facts = items_repo.get_access_facts(session, tenant_id=user.tenant_id, item_id=item_id)
    if facts is None or not can(session, user_id=user.id, action="read", item=facts):
        raise HTTPException(status_code=404, detail="not found")
    if action != "read" and not can(session, user_id=user.id, action=action, item=facts):
        raise HTTPException(status_code=403, detail="not allowed")


def _require_no_reverse_references(session: Session, *, tenant_id: str, item_id: str) -> None:
    # SP-42/F-coeur-contenu-04 : sans cette garde, DELETE /items/{id} (ou
    # /configs/by-item/{id}) supprimait un Dataset/Bookmark/Pipeline encore
    # référencé par une AlertRule/un ReportSchedule/un autre Dataset,
    # laissant une config orpheline silencieuse (204, aucun signal).
    referencing = repo.find_referencing_config_kinds(session, tenant_id=tenant_id, item_id=item_id)
    if referencing:
        raise HTTPException(
            status_code=409,
            detail=f"still referenced by config kind(s): {', '.join(referencing)}",
        )


def _delete_config_and_item(session: Session, config_id: str, item_id: str, tenant_id: str) -> None:
    from sqlalchemy import delete

    from app.configs.models import Config, ConfigRevision
    from app.sharing.models import ItemShare

    session.execute(delete(ConfigRevision).where(ConfigRevision.config_id == config_id))
    session.execute(delete(Config).where(Config.id == config_id))
    session.execute(delete(ItemShare).where(ItemShare.item_id == item_id))
    session.execute(delete(Item).where(Item.id == item_id, Item.tenant_id == tenant_id))
    session.flush()


def _validate_extension_scope(session: Session, config: BuilderConfig, *, tenant_id: str) -> None:
    try:
        validate_extension_permissions(session, config, tenant_id=tenant_id)
    except ExtensionPermissionError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err


def _require_etl_enabled_for_pipeline(config: BuilderConfig) -> None:
    if config.kind == "pipeline" and not is_etl_enabled():
        raise HTTPException(status_code=403, detail="ETL capability disabled on this instance")


def _require_export_enabled_for_report(config: BuilderConfig) -> None:
    # Jumeau de la garde pipeline/ETL ci-dessus (revue finale SP-17b, I3) :
    # sur une instance sans capacité export, un ReportSchedule pouvait être
    # créé mais son rendu restait "pending" à jamais — rien ne dépile la file
    # `export`, et export_repo.reclaim_stuck_jobs ne récupère que les
    # "running". Mieux vaut refuser la création tout de suite.
    if config.kind == "report" and not is_export_enabled():
        raise HTTPException(status_code=403, detail="Export capability disabled on this instance")


# SP-43 Étape 1 : le mapping kind->privilège vit désormais dans
# app.roles.kind_registry (privilege_for_kind), seule source de vérité,
# consommée aussi par app.mcp.tools, app.tileset3d.routes,
# app.terrain3d.routes et app.pipelines.routes — remplace le dict privé qui
# vivait ici et que ces 4 autres sites couplaient chacun différemment (import
# de nom privé, import du dict lui-même, recopie de valeur en dur), un défaut
# rouvert 3 fois avant SP-42 (cf. spec SP-43 §1.1). Rationale du mapping
# lui-même : voir la docstring de kind_registry.py.
def _require_privilege_for_kind(session: Session, user: User, config: BuilderConfig) -> None:
    require_privilege(session, user, privilege_for_kind(config.kind))


# SP-42, revue des lots de correctifs 2/3bis (point 3, Important) :
# _require_privilege_for_kind ci-dessus se cale sur le kind SOUMIS dans la
# requête, jamais sur celui déjà enregistré pour cet item — repo.update_config
# ne compare (et ne mute) jamais Config.kind (vérifié par lecture directe de
# app/configs/repository.py). Qui détient `write` sur un item "map" mais
# seulement analytics.view (pas maps.manage — cas réel : l'Analyste) pouvait
# donc écraser la config de cette map en soumettant kind="bookmark" : la
# garde consultait alors le privilège du kind soumis, pas celui de l'item.
# Sur toute mise à jour d'une config déjà existante (jamais à la création,
# où il n'existe encore aucun kind enregistré à comparer), le kind soumis
# doit être identique à celui déjà enregistré — sinon 400, avant même de
# consulter le catalogue de privilèges.
def _require_kind_matches_existing(existing_kind: str, submitted_kind: str) -> None:
    if submitted_kind != existing_kind:
        raise HTTPException(
            status_code=400,
            detail=(
                f"config kind cannot change on update: item is '{existing_kind}', "
                f"got '{submitted_kind}'"
            ),
        )


@router.post("/configs", response_model=ConfigRead, status_code=status.HTTP_201_CREATED)
def create_config(
    request: CreateConfigRequest,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> ConfigRead:
    _require_privilege_for_kind(session, user, request.config)
    _require_etl_enabled_for_pipeline(request.config)
    _require_export_enabled_for_report(request.config)
    _validate_extension_scope(session, request.config, tenant_id=user.tenant_id)
    _validate_dataset_payload(session, request.config, user=user)
    _validate_bookmark_payload(session, request.config, user=user)
    _validate_pipeline_payload(session, request.config, user=user)
    _validate_alert_payload(session, request.config, user=user)
    _validate_report_payload(session, request.config, user=user)
    _validate_tileset3d_payload(session, request.config, user=user)
    _validate_terrain3d_payload(session, request.config, user=user)
    try:
        item = items_repo.create_item(
            session,
            tenant_id=user.tenant_id,
            owner_id=user.id,
            resource_type=request.config.kind,
            title=request.title,
            slug=request.slug,
        )
    except SlugCollisionError as err:
        raise HTTPException(status_code=409, detail=str(err)) from err
    except InvalidSlugError as err:
        raise HTTPException(status_code=422, detail=str(err)) from err
    result = repo.create_config(session, request.config, item_id=item.id, tenant_id=user.tenant_id)
    write_audit(
        session,
        tenant_id=user.tenant_id,
        actor_id=user.id,
        actor_kind="user",
        action="config.create",
        object_type="config",
        object_id=result.id,
        payload={"title": request.title, "kind": request.config.kind},
    )
    write_audit(
        session,
        tenant_id=user.tenant_id,
        actor_id=user.id,
        actor_kind="user",
        action="item.create",
        object_type="item",
        object_id=item.id,
        payload={"title": request.title},
    )
    return result


@router.get("/configs/{config_id}", response_model=ConfigRead)
def get_config(
    config_id: str,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> ConfigRead:
    result = repo.get_config(session, config_id)
    if result is None or result.itemId is None:
        raise HTTPException(status_code=404, detail="config not found")
    _require_access(session, user=user, item_id=result.itemId, action="read")
    return result


@router.put("/configs/{config_id}", response_model=ConfigRead)
def update_config(
    config_id: str,
    config: BuilderConfig,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> ConfigRead:
    existing = repo.get_config(session, config_id)
    if existing is None or existing.itemId is None:
        raise HTTPException(status_code=404, detail="config not found")
    _require_access(session, user=user, item_id=existing.itemId, action="write")
    _require_kind_matches_existing(existing.kind, config.kind)
    _require_privilege_for_kind(session, user, config)
    _require_etl_enabled_for_pipeline(config)
    _require_export_enabled_for_report(config)
    _validate_extension_scope(session, config, tenant_id=user.tenant_id)
    _validate_dataset_payload(session, config, user=user)
    _validate_bookmark_payload(session, config, user=user)
    _validate_pipeline_payload(session, config, user=user)
    _validate_alert_payload(session, config, user=user)
    _validate_report_payload(session, config, user=user)
    _validate_tileset3d_payload(session, config, user=user)
    _validate_terrain3d_payload(session, config, user=user)

    result = repo.update_config(session, config_id, config, tenant_id=user.tenant_id)
    if result is None:
        raise HTTPException(status_code=404, detail="config not found")
    write_audit(
        session,
        tenant_id=user.tenant_id,
        actor_id=user.id,
        actor_kind="user",
        action="config.update",
        object_type="config",
        object_id=config_id,
        payload={},
    )
    return result


@router.get("/configs/{config_id}/revisions", response_model=list[RevisionInfo])
def list_revisions(
    config_id: str,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> list[RevisionInfo]:
    existing = repo.get_config(session, config_id)
    if existing is None or existing.itemId is None:
        raise HTTPException(status_code=404, detail="config not found")
    _require_access(session, user=user, item_id=existing.itemId, action="read")
    return repo.list_revisions(session, config_id)


@router.post("/configs/{config_id}/rollback", response_model=ConfigRead)
def rollback_config(
    config_id: str,
    request: RollbackRequest,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> ConfigRead:
    existing = repo.get_config(session, config_id)
    if existing is None or existing.itemId is None:
        raise HTTPException(status_code=404, detail="config not found")
    _require_access(session, user=user, item_id=existing.itemId, action="write")

    # Le rollback écrit une nouvelle version comme le ferait un PUT, mais
    # sans repasser par aucun validateur de payload — un trou théorique tant
    # que rien n'appelait cette route, réel depuis que le panneau
    # « Historique » (SP-23) la câble sur les cinq éditeurs. Une vieille
    # version peut référencer une collection supprimée depuis, ou une
    # capacité éteinte depuis. On valide donc la config restaurée AVANT de
    # l'écrire, avec exactement la même séquence que update_config.
    candidate = repo.get_revision_config(session, config_id, request.version)
    if candidate is None:
        raise HTTPException(status_code=404, detail="config or version not found")
    # SP-42, revue du lot de correctifs 1 (Important) : même trou que
    # create_config/update_config avant eafb02cc, resté ouvert ici — le
    # rollback rejoue "exactement la même séquence que update_config" (cf.
    # commentaire ci-dessus) mais sautait ce garde. Volontairement APRÈS
    # _require_access (mêmes ordres que create_config/update_config) et
    # HORS du try/except ci-dessous : un privilège manquant est un refus
    # d'autorisation (403), pas un problème de validité de la version
    # restaurée (422) — les deux ne doivent pas se confondre.
    #
    # SP-42, revue des lots de correctifs 2/3bis (point 3) : même défense en
    # profondeur qu'update_config/update_config_by_item ci-dessous — une
    # révision stockée dont le kind diverge de celui de l'item (Config.kind,
    # jamais muté par repo.update_config) ne peut apparaître qu'à travers une
    # exploitation historique du même défaut ou un accès direct au
    # repository ; /rollback ne doit pas la restaurer. Même raison de rang
    # (400, hors du try/except) que le garde de privilège juste après.
    _require_kind_matches_existing(existing.kind, candidate.kind)
    _require_privilege_for_kind(session, user, candidate)
    try:
        _require_etl_enabled_for_pipeline(candidate)
        _require_export_enabled_for_report(candidate)
        _validate_extension_scope(session, candidate, tenant_id=user.tenant_id)
        _validate_dataset_payload(session, candidate, user=user)
        _validate_bookmark_payload(session, candidate, user=user)
        _validate_pipeline_payload(session, candidate, user=user)
        _validate_alert_payload(session, candidate, user=user)
        _validate_report_payload(session, candidate, user=user)
        _validate_tileset3d_payload(session, candidate, user=user)
        _validate_terrain3d_payload(session, candidate, user=user)
    except HTTPException as exc:
        raise HTTPException(
            status_code=422,
            detail=(
                f"la version {request.version} n'est plus valide et ne peut pas "
                f"être restaurée : {exc.detail}"
            ),
        ) from exc

    result = repo.rollback_config(session, config_id, request.version, tenant_id=user.tenant_id)
    if result is None:
        raise HTTPException(status_code=404, detail="config or version not found")
    write_audit(
        session,
        tenant_id=user.tenant_id,
        actor_id=user.id,
        actor_kind="user",
        action="config.rollback",
        object_type="config",
        object_id=config_id,
        payload={"restored_version": request.version},
    )
    return result


@router.delete("/configs/{config_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_config(
    config_id: str,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> Response:
    result = repo.get_config(session, config_id)
    if result is None or result.itemId is None:
        raise HTTPException(status_code=404, detail="config not found")
    _require_access(session, user=user, item_id=result.itemId, action="delete")
    # SP-42, revue de la dernière passe de correctifs (point 6, Important) :
    # can()/_require_access(action="delete") autorise déjà un partage
    # "editor" — sans jamais consulter le privilège de domaine du kind
    # ENREGISTRÉ (même garde que _require_privilege_for_kind sur PUT). Un
    # Lecteur (0 privilège) à qui une map est partagée en editor détruisait
    # donc une map qu'il n'a pas le droit d'éditer.
    _require_privilege_for_kind(session, user, result.config)

    _delete_config_and_item(session, config_id, result.itemId, user.tenant_id)
    write_audit(
        session,
        tenant_id=user.tenant_id,
        actor_id=user.id,
        actor_kind="user",
        action="config.delete",
        object_type="config",
        object_id=config_id,
        payload={},
    )
    write_audit(
        session,
        tenant_id=user.tenant_id,
        actor_id=user.id,
        actor_kind="user",
        action="item.delete",
        object_type="item",
        object_id=result.itemId,
        payload={},
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/configs/by-item/{item_id}", response_model=ConfigRead)
def get_config_by_item(
    item_id: str,
    mode: str | None = None,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> ConfigRead:
    _require_access(session, user=user, item_id=item_id, action="read")
    result = repo.get_config_by_item(session, item_id)
    if result is None:
        raise HTTPException(status_code=404, detail="config not found")
    if mode == "runtime":
        _apps_runtime_executions_counter.add(1)
    return result


@router.put("/configs/by-item/{item_id}", response_model=ConfigRead)
def update_config_by_item(
    item_id: str,
    config: BuilderConfig,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> ConfigRead:
    _require_access(session, user=user, item_id=item_id, action="write")
    existing = repo.get_config_by_item(session, item_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="config not found")
    _require_kind_matches_existing(existing.kind, config.kind)
    _require_privilege_for_kind(session, user, config)
    _require_etl_enabled_for_pipeline(config)
    _require_export_enabled_for_report(config)
    _validate_extension_scope(session, config, tenant_id=user.tenant_id)
    _validate_dataset_payload(session, config, user=user)
    _validate_bookmark_payload(session, config, user=user)
    _validate_pipeline_payload(session, config, user=user)
    _validate_alert_payload(session, config, user=user)
    _validate_report_payload(session, config, user=user)
    _validate_tileset3d_payload(session, config, user=user)
    _validate_terrain3d_payload(session, config, user=user)
    result = repo.update_config(session, existing.id, config, tenant_id=user.tenant_id)
    if result is None:
        raise HTTPException(status_code=404, detail="config not found")
    write_audit(
        session,
        tenant_id=user.tenant_id,
        actor_id=user.id,
        actor_kind="user",
        action="config.update",
        object_type="config",
        object_id=existing.id,
        payload={},
    )
    return result


@router.delete("/configs/by-item/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_config_by_item(
    item_id: str,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> Response:
    _require_access(session, user=user, item_id=item_id, action="delete")
    result = repo.get_config_by_item(session, item_id)
    if result is None:
        raise HTTPException(status_code=404, detail="config not found")
    # SP-42, revue de la dernière passe de correctifs (point 6, Important) :
    # cf. commentaire jumeau sur delete_config ci-dessus.
    _require_privilege_for_kind(session, user, result.config)
    _require_no_reverse_references(session, tenant_id=user.tenant_id, item_id=item_id)
    _delete_config_and_item(session, result.id, item_id, user.tenant_id)
    write_audit(
        session,
        tenant_id=user.tenant_id,
        actor_id=user.id,
        actor_kind="user",
        action="config.delete",
        object_type="config",
        object_id=result.id,
        payload={},
    )
    write_audit(
        session,
        tenant_id=user.tenant_id,
        actor_id=user.id,
        actor_kind="user",
        action="item.delete",
        object_type="item",
        object_id=item_id,
        payload={},
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_item(
    item_id: str,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> Response:
    # Lives here, not in app/items/routes.py: deleting an item must also clear
    # its config_revisions before the DB cascades configs -> items (see plan
    # Architecture). app.items must never import app.configs, so this
    # cross-cutting orchestration belongs to the configs layer.
    _require_access(session, user=user, item_id=item_id, action="delete")
    result = repo.get_config_by_item(session, item_id)
    if result is None:
        raise HTTPException(status_code=404, detail="item not found")
    # SP-42, revue de la dernière passe de correctifs (point 6, Important) :
    # cf. commentaire jumeau sur delete_config ci-dessus.
    _require_privilege_for_kind(session, user, result.config)
    _require_no_reverse_references(session, tenant_id=user.tenant_id, item_id=item_id)
    _delete_config_and_item(session, result.id, item_id, user.tenant_id)
    write_audit(
        session,
        tenant_id=user.tenant_id,
        actor_id=user.id,
        actor_kind="user",
        action="item.delete",
        object_type="item",
        object_id=item_id,
        payload={},
    )
    write_audit(
        session,
        tenant_id=user.tenant_id,
        actor_id=user.id,
        actor_kind="user",
        action="config.delete",
        object_type="config",
        object_id=result.id,
        payload={},
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
