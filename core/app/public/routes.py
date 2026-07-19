# SPDX-License-Identifier: Apache-2.0
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.configs import repository as configs_repo
from app.configs.repository import ConfigRead
from app.db import get_session
from app.items import repository as items_repo
from app.items.schemas import ItemPage, ItemRead

router = APIRouter(prefix="/public")


@router.get("/items", response_model=ItemPage)
def list_public_items(
    type: str | None = None,
    tag: str | None = None,
    page: int = 1,
    pageSize: int = 12,
    session: Session = Depends(get_session),
) -> ItemPage:
    return items_repo.list_published_items(
        session, resource_type=type, tag=tag, page=page, page_size=pageSize,
    )


@router.get("/items/{item_id}", response_model=ItemRead)
def get_public_item(item_id: str, session: Session = Depends(get_session)) -> ItemRead:
    result = items_repo.get_published_item(session, item_id=item_id)
    if result is None:
        raise HTTPException(status_code=404, detail="item not found")
    return result


@router.get("/sites/{slug}", response_model=ItemRead)
def get_public_site(slug: str, session: Session = Depends(get_session)) -> ItemRead:
    result = items_repo.get_published_site_by_slug(session, slug=slug)
    if result is None:
        raise HTTPException(status_code=404, detail="site not found")
    return result


@router.get("/configs/by-item/{item_id}", response_model=ConfigRead)
def get_public_config_by_item(item_id: str, session: Session = Depends(get_session)) -> ConfigRead:
    item = items_repo.get_published_item(session, item_id=item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="item not found")
    result = configs_repo.get_config_by_item(session, item_id)
    if result is None:
        raise HTTPException(status_code=404, detail="config not found")
    return result
