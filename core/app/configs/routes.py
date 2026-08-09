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
from app.configs.pipeline_validation import validate_pipeline_payload as _validate_pipeline_payload
from app.configs.report_validation import validate_report_payload as _validate_report_payload
from app.configs.repository import ConfigRead, RevisionInfo
from app.configs.schemas import BuilderConfig
from app.configs.extension_permissions import ExtensionPermissionError, validate_extension_permissions
from app.db import get_session
from app.items import repository as items_repo
from app.items.models import Item
from app.items.slug import InvalidSlugError, SlugCollisionError
from app.sharing.authorization import can
from app.users.models import User

router = APIRouter()

_meter = metrics.get_meter(__name__)
_apps_runtime_executions_counter = _meter.create_counter(
    "geostudio.apps.runtime_executions", unit="1", description="GET config calls with mode=runtime",
)


class CreateConfigRequest(BaseModel):
    title: str
    config: BuilderConfig
    slug: str | None = None


class RollbackRequest(BaseModel):
    version: int


def _require_access(
    session: Session, *, user: User, item_id: str, action: str
) -> None:
    facts = items_repo.get_access_facts(session, tenant_id=user.tenant_id, item_id=item_id)
    if facts is None or not can(session, user_id=user.id, action="read", item=facts):
        raise HTTPException(status_code=404, detail="not found")
    if action != "read" and not can(session, user_id=user.id, action=action, item=facts):
        raise HTTPException(status_code=403, detail="not allowed")


def _delete_config_and_item(session: Session, config_id: str, item_id: str, tenant_id: str) -> None:
    from sqlalchemy import delete
    from app.configs.models import ConfigRevision, Config
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


@router.post("/configs", response_model=ConfigRead, status_code=status.HTTP_201_CREATED)
def create_config(
    request: CreateConfigRequest,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> ConfigRead:
    _require_etl_enabled_for_pipeline(request.config)
    _require_export_enabled_for_report(request.config)
    _validate_extension_scope(session, request.config, tenant_id=user.tenant_id)
    _validate_dataset_payload(session, request.config, user=user)
    _validate_bookmark_payload(session, request.config, user=user)
    _validate_pipeline_payload(session, request.config, user=user)
    _validate_alert_payload(session, request.config, user=user)
    _validate_report_payload(session, request.config, user=user)
    try:
        item = items_repo.create_item(
            session, tenant_id=user.tenant_id, owner_id=user.id,
            resource_type=request.config.kind, title=request.title,
            slug=request.slug,
        )
    except SlugCollisionError as err:
        raise HTTPException(status_code=409, detail=str(err)) from err
    except InvalidSlugError as err:
        raise HTTPException(status_code=422, detail=str(err)) from err
    result = repo.create_config(session, request.config, item_id=item.id, tenant_id=user.tenant_id)
    write_audit(
        session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="user",
        action="config.create", object_type="config", object_id=result.id,
        payload={"title": request.title, "kind": request.config.kind},
    )
    write_audit(
        session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="user",
        action="item.create", object_type="item", object_id=item.id,
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
    _require_etl_enabled_for_pipeline(config)
    _require_export_enabled_for_report(config)
    _validate_extension_scope(session, config, tenant_id=user.tenant_id)
    _validate_dataset_payload(session, config, user=user)
    _validate_bookmark_payload(session, config, user=user)
    _validate_pipeline_payload(session, config, user=user)
    _validate_alert_payload(session, config, user=user)
    _validate_report_payload(session, config, user=user)

    result = repo.update_config(session, config_id, config, tenant_id=user.tenant_id)
    if result is None:
        raise HTTPException(status_code=404, detail="config not found")
    write_audit(
        session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="user",
        action="config.update", object_type="config", object_id=config_id, payload={},
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

    result = repo.rollback_config(session, config_id, request.version, tenant_id=user.tenant_id)
    if result is None:
        raise HTTPException(status_code=404, detail="config or version not found")
    write_audit(
        session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="user",
        action="config.rollback", object_type="config", object_id=config_id,
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

    _delete_config_and_item(session, config_id, result.itemId, user.tenant_id)
    write_audit(
        session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="user",
        action="config.delete", object_type="config", object_id=config_id, payload={},
    )
    write_audit(
        session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="user",
        action="item.delete", object_type="item", object_id=result.itemId, payload={},
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
    _require_etl_enabled_for_pipeline(config)
    _require_export_enabled_for_report(config)
    _validate_extension_scope(session, config, tenant_id=user.tenant_id)
    _validate_dataset_payload(session, config, user=user)
    _validate_bookmark_payload(session, config, user=user)
    _validate_pipeline_payload(session, config, user=user)
    _validate_alert_payload(session, config, user=user)
    _validate_report_payload(session, config, user=user)
    result = repo.update_config(session, existing.id, config, tenant_id=user.tenant_id)
    if result is None:
        raise HTTPException(status_code=404, detail="config not found")
    write_audit(
        session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="user",
        action="config.update", object_type="config", object_id=existing.id, payload={},
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
    _delete_config_and_item(session, result.id, item_id, user.tenant_id)
    write_audit(
        session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="user",
        action="config.delete", object_type="config", object_id=result.id, payload={},
    )
    write_audit(
        session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="user",
        action="item.delete", object_type="item", object_id=item_id, payload={},
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
    _delete_config_and_item(session, result.id, item_id, user.tenant_id)
    write_audit(
        session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="user",
        action="item.delete", object_type="item", object_id=item_id, payload={},
    )
    write_audit(
        session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="user",
        action="config.delete", object_type="config", object_id=result.id, payload={},
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
