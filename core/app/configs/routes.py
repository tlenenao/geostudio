from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.audit.writer import write_audit
from app.auth.dependency import get_current_user
from app.configs import repository as repo
from app.configs.repository import ConfigRead, RevisionInfo
from app.configs.schemas import BuilderConfig
from app.db import get_session
from app.geonode import ItemClient, StubItemClient
from app.users.models import User

router = APIRouter()

# Default providers; create_app() overrides get_session with a real factory,
# and tests override both via app.dependency_overrides.
_default_item_client = StubItemClient()


def get_item_client() -> ItemClient:
    return _default_item_client


class CreateConfigRequest(BaseModel):
    title: str
    owner: str
    config: BuilderConfig


class RollbackRequest(BaseModel):
    version: int


@router.post("/configs", response_model=ConfigRead, status_code=status.HTTP_201_CREATED)
def create_config(
    request: CreateConfigRequest,
    session: Session = Depends(get_session),
    items: ItemClient = Depends(get_item_client),
    user: User = Depends(get_current_user),
) -> ConfigRead:
    item_id = items.create_item(
        title=request.title, type=request.config.kind, owner=request.owner
    )
    result = repo.create_config(session, request.config, item_id=item_id)
    write_audit(
        session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="user",
        action="config.create", object_type="config", object_id=result.id,
        payload={"title": request.title, "kind": request.config.kind},
    )
    return result


@router.get("/configs/{config_id}", response_model=ConfigRead)
def get_config(config_id: str, session: Session = Depends(get_session)) -> ConfigRead:
    result = repo.get_config(session, config_id)
    if result is None:
        raise HTTPException(status_code=404, detail="config not found")
    return result


@router.put("/configs/{config_id}", response_model=ConfigRead)
def update_config(
    config_id: str,
    config: BuilderConfig,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> ConfigRead:
    result = repo.update_config(session, config_id, config)
    if result is None:
        raise HTTPException(status_code=404, detail="config not found")
    write_audit(
        session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="user",
        action="config.update", object_type="config", object_id=config_id, payload={},
    )
    return result


@router.get("/configs/{config_id}/revisions", response_model=list[RevisionInfo])
def list_revisions(
    config_id: str, session: Session = Depends(get_session)
) -> list[RevisionInfo]:
    return repo.list_revisions(session, config_id)


@router.post("/configs/{config_id}/rollback", response_model=ConfigRead)
def rollback_config(
    config_id: str,
    request: RollbackRequest,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> ConfigRead:
    result = repo.rollback_config(session, config_id, request.version)
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
    items: ItemClient = Depends(get_item_client),
    user: User = Depends(get_current_user),
) -> Response:
    result = repo.get_config(session, config_id)
    if result is None:
        raise HTTPException(status_code=404, detail="config not found")
    # GeoNode item is deleted before the DB config; if delete_item raises, the
    # config is preserved (no silent orphan). The reverse (GeoNode gone, DB write
    # fails) is an accepted, unlikely distributed-systems window.
    if result.itemId:
        items.delete_item(result.itemId)
    repo.delete_config(session, config_id)
    write_audit(
        session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="user",
        action="config.delete", object_type="config", object_id=config_id, payload={},
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/configs/by-item/{item_id}", response_model=ConfigRead)
def get_config_by_item(
    item_id: str, session: Session = Depends(get_session)
) -> ConfigRead:
    result = repo.get_config_by_item(session, item_id)
    if result is None:
        raise HTTPException(status_code=404, detail="config not found")
    return result


@router.put("/configs/by-item/{item_id}", response_model=ConfigRead)
def update_config_by_item(
    item_id: str,
    config: BuilderConfig,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> ConfigRead:
    existing = repo.get_config_by_item(session, item_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="config not found")
    result = repo.update_config(session, existing.id, config)
    if result is None:
        raise HTTPException(status_code=404, detail="config not found")
    write_audit(
        session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="user",
        action="config.update", object_type="config", object_id=existing.id, payload={},
    )
    return result


@router.delete(
    "/configs/by-item/{item_id}", status_code=status.HTTP_204_NO_CONTENT
)
def delete_config_by_item(
    item_id: str,
    session: Session = Depends(get_session),
    items: ItemClient = Depends(get_item_client),
    user: User = Depends(get_current_user),
) -> Response:
    result = repo.get_config_by_item(session, item_id)
    if result is None:
        raise HTTPException(status_code=404, detail="config not found")
    if result.itemId:
        items.delete_item(result.itemId)
    repo.delete_config(session, result.id)
    write_audit(
        session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="user",
        action="config.delete", object_type="config", object_id=result.id, payload={},
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
