# SPDX-License-Identifier: Apache-2.0
from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile, status
from sqlalchemy.orm import Session

from app.audit.writer import write_audit
from app.auth.dependency import get_current_user
from app.db import get_session
from app.items import repository as repo
from app.items.schemas import ItemPage, ItemRead, ItemUpdatePatch
from app.items.service import get_item_service, get_sharing_service, set_sharing_service
from app.items.slug import InvalidSlugError, SlugCollisionError
from app.items.storage import InMemoryThumbnailStore, ThumbnailStore
from app.sharing.authorization import can
from app.sharing.schemas import Sharing
from app.users.models import User

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
    page: int = Query(1, ge=1),
    # Pas de borne haute : shell/src/api/itemClient.ts appelle déjà cette
    # route avec pageSize=200 (sélecteurs de sources tileset3d/terrain3d) —
    # vérifié avant d'écrire ce correctif (piège n°3 : le fix suggéré par la
    # falsification citait `Query(100, ge=1)` de features/routes.py comme
    # précédent mais lui ajoutait un `le=100` que ce précédent n'a pas).
    pageSize: int = Query(12, ge=1),
    sort: str | None = None,
    owner: str | None = None,
    keyword: list[str] | None = Query(default=None),
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> ItemPage:
    return repo.list_items(
        session,
        tenant_id=user.tenant_id,
        current_user_id=user.id,
        q=q,
        resource_type=type,
        scope=scope,
        page=page,
        page_size=pageSize,
        sort=sort,
        owner=owner,
        keywords=keyword,
    )


@router.get("/items/{item_id}", response_model=ItemRead)
def get_item(
    item_id: str,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> ItemRead:
    return get_item_service(session, item_id=item_id, user=user)


@router.patch("/items/{item_id}", response_model=ItemRead)
def update_item(
    item_id: str,
    patch: ItemUpdatePatch,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> ItemRead:
    facts = repo.get_access_facts(session, tenant_id=user.tenant_id, item_id=item_id)
    if facts is None or not can(session, user_id=user.id, action="read", item=facts):
        raise HTTPException(status_code=404, detail="item not found")
    if not can(session, user_id=user.id, action="write", item=facts):
        raise HTTPException(status_code=403, detail="not allowed to modify this item")

    try:
        result = repo.update_item(
            session,
            tenant_id=user.tenant_id,
            item_id=item_id,
            title=patch.title,
            abstract=patch.abstract,
            keywords=patch.keywords,
            is_published=patch.isPublished,
            slug=patch.slug,
            license=patch.license,
            language=patch.language,
            current_user_id=user.id,
        )
    except SlugCollisionError as err:
        raise HTTPException(status_code=409, detail=str(err)) from err
    except InvalidSlugError as err:
        raise HTTPException(status_code=422, detail=str(err)) from err
    if result is None:
        raise HTTPException(status_code=404, detail="item not found")

    if patch.isPublished is True:
        action = "item.publish"
    elif patch.isPublished is False:
        action = "item.unpublish"
    else:
        action = "item.update"
    write_audit(
        session,
        tenant_id=user.tenant_id,
        actor_id=user.id,
        actor_kind="user",
        action=action,
        object_type="item",
        object_id=item_id,
        payload={},
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
    facts = repo.get_access_facts(session, tenant_id=user.tenant_id, item_id=item_id)
    if facts is None or not can(session, user_id=user.id, action="read", item=facts):
        raise HTTPException(status_code=404, detail="item not found")
    if not can(session, user_id=user.id, action="write", item=facts):
        raise HTTPException(status_code=403, detail="not allowed to modify this item")

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
    facts = repo.get_access_facts(session, tenant_id=user.tenant_id, item_id=item_id)
    if facts is None or not can(session, user_id=user.id, action="read", item=facts):
        raise HTTPException(status_code=404, detail="item not found")
    key = repo.get_thumbnail_key(session, tenant_id=user.tenant_id, item_id=item_id)
    if key is None:
        raise HTTPException(status_code=404, detail="no thumbnail")
    content, content_type = store.read(key)
    return Response(content=content, media_type=content_type)


@router.get("/items/{item_id}/sharing", response_model=Sharing)
def get_sharing(
    item_id: str,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> Sharing:
    return get_sharing_service(session, item_id=item_id, user=user)


@router.put("/items/{item_id}/sharing", status_code=status.HTTP_204_NO_CONTENT)
def set_sharing(
    item_id: str,
    body: Sharing,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> Response:
    set_sharing_service(session, item_id=item_id, user=user, sharing=body)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
