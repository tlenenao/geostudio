from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status

from app.audit.writer import write_audit
from app.auth.dependency import get_current_user
from app.db import get_session
from app.items import repository as repo
from app.items.schemas import ItemPage, ItemRead, ItemUpdatePatch
from app.items.storage import InMemoryThumbnailStore, ThumbnailStore
from app.users.models import User
from sqlalchemy.orm import Session

router = APIRouter()

_default_thumbnail_store: ThumbnailStore = InMemoryThumbnailStore()


def get_thumbnail_store() -> ThumbnailStore:
    return _default_thumbnail_store


_MAX_THUMBNAIL_BYTES = 2 * 1024 * 1024


@router.get("/items", response_model=ItemPage)
def list_items(
    q: str | None = None,
    type: str | None = None,
    scope: str = "all",
    page: int = 1,
    pageSize: int = 12,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> ItemPage:
    return repo.list_items(
        session, tenant_id=user.tenant_id, current_user_id=user.id,
        q=q, resource_type=type, scope=scope, page=page, page_size=pageSize,
    )


@router.get("/items/{item_id}", response_model=ItemRead)
def get_item(
    item_id: str,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> ItemRead:
    result = repo.get_item(session, tenant_id=user.tenant_id, item_id=item_id)
    if result is None:
        raise HTTPException(status_code=404, detail="item not found")
    return result


@router.patch("/items/{item_id}", response_model=ItemRead)
def update_item(
    item_id: str,
    patch: ItemUpdatePatch,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> ItemRead:
    result = repo.update_item(
        session, tenant_id=user.tenant_id, item_id=item_id,
        title=patch.title, abstract=patch.abstract, keywords=patch.keywords,
        is_published=patch.isPublished,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="item not found")

    if patch.isPublished is True:
        action = "item.publish"
    elif patch.isPublished is False:
        action = "item.unpublish"
    else:
        action = "item.update"
    write_audit(
        session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="user",
        action=action, object_type="item", object_id=item_id, payload={},
    )
    return result


@router.post("/items/{item_id}/thumbnail", status_code=status.HTTP_204_NO_CONTENT)
def upload_thumbnail(
    item_id: str,
    file: UploadFile = File(...),
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
    store: ThumbnailStore = Depends(get_thumbnail_store),
) -> Response:
    existing = repo.get_item(session, tenant_id=user.tenant_id, item_id=item_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="item not found")

    content_type = file.content_type or "application/octet-stream"
    if not content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="file must be an image")
    content = file.file.read()
    if len(content) > _MAX_THUMBNAIL_BYTES:
        raise HTTPException(status_code=413, detail="thumbnail too large")

    key = f"{item_id}.bin"
    store.upload(key, content, content_type)
    repo.set_thumbnail_key(session, tenant_id=user.tenant_id, item_id=item_id, thumbnail_key=key)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/items/{item_id}/thumbnail")
def read_thumbnail(
    item_id: str,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
    store: ThumbnailStore = Depends(get_thumbnail_store),
) -> Response:
    key = repo.get_thumbnail_key(session, tenant_id=user.tenant_id, item_id=item_id)
    if key is None:
        raise HTTPException(status_code=404, detail="no thumbnail")
    content, content_type = store.read(key)
    return Response(content=content, media_type=content_type)
