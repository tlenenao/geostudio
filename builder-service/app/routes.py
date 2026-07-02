from collections.abc import Iterator

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app import repository as repo
from app.geonode import ItemClient, StubItemClient
from app.repository import ConfigRead, RevisionInfo
from app.schemas import BuilderConfig

router = APIRouter()

# Default providers; create_app() overrides get_session with a real factory,
# and tests override both via app.dependency_overrides.
_default_item_client = StubItemClient()


def get_session() -> Iterator[Session]:  # pragma: no cover - overridden at runtime
    raise RuntimeError("get_session dependency not configured")


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
) -> ConfigRead:
    item_id = items.create_item(
        title=request.title, type=request.config.kind, owner=request.owner
    )
    return repo.create_config(session, request.config, item_id=item_id)


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
) -> ConfigRead:
    result = repo.update_config(session, config_id, config)
    if result is None:
        raise HTTPException(status_code=404, detail="config not found")
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
) -> ConfigRead:
    result = repo.rollback_config(session, config_id, request.version)
    if result is None:
        raise HTTPException(status_code=404, detail="config or version not found")
    return result


@router.delete("/configs/{config_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_config(
    config_id: str,
    session: Session = Depends(get_session),
    items: ItemClient = Depends(get_item_client),
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
) -> ConfigRead:
    existing = repo.get_config_by_item(session, item_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="config not found")
    result = repo.update_config(session, existing.id, config)
    if result is None:
        raise HTTPException(status_code=404, detail="config not found")
    return result


@router.delete(
    "/configs/by-item/{item_id}", status_code=status.HTTP_204_NO_CONTENT
)
def delete_config_by_item(
    item_id: str,
    session: Session = Depends(get_session),
    items: ItemClient = Depends(get_item_client),
) -> Response:
    result = repo.get_config_by_item(session, item_id)
    if result is None:
        raise HTTPException(status_code=404, detail="config not found")
    if result.itemId:
        items.delete_item(result.itemId)
    repo.delete_config(session, result.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
