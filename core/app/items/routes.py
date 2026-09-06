# SPDX-License-Identifier: Apache-2.0
import os

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
from app.sharing import repository as sharing_repo
from app.sharing.authorization import can
from app.sharing.schemas import (
    CreateShareLinkRequest,
    ResolvedShareLink,
    ShareLinkCreated,
    ShareLinkListItem,
    Sharing,
)
from app.sharing.share_links import (
    ShareLinkTokenError,
    decode_share_link_token,
    mint_share_link_token,
)
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


def _require_share_access(session: Session, *, item_id: str, user: User):
    """Même garde que set_sharing_service (get_sharing_service.py) : lisible
    (404 sinon) ET partageable (403 sinon) — un lien de partage est une
    forme de partage, il suit exactement la même autorisation que le
    partage groupe/rôle plat."""
    facts = repo.get_access_facts(session, tenant_id=user.tenant_id, item_id=item_id)
    if facts is None or not can(session, user_id=user.id, action="read", item=facts):
        raise HTTPException(status_code=404, detail="item not found")
    if not can(session, user_id=user.id, action="share", item=facts):
        raise HTTPException(status_code=403, detail="not allowed to share this item")


@router.post(
    "/items/{item_id}/share-links",
    response_model=ShareLinkCreated,
    status_code=status.HTTP_201_CREATED,
)
def create_share_link_route(
    item_id: str,
    body: CreateShareLinkRequest,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> ShareLinkCreated:
    _require_share_access(session, item_id=item_id, user=user)
    ttl_seconds = body.ttlDays * 86400
    link = sharing_repo.create_share_link(
        session,
        tenant_id=user.tenant_id,
        item_id=item_id,
        created_by=user.id,
        ttl_seconds=ttl_seconds,
    )
    token = mint_share_link_token(
        share_link_id=link.id, tenant_id=user.tenant_id, item_id=item_id, ttl_seconds=ttl_seconds
    )
    write_audit(
        session,
        tenant_id=user.tenant_id,
        actor_id=user.id,
        actor_kind="user",
        action="share_link.create",
        object_type="share_link",
        object_id=link.id,
        payload={"itemId": item_id, "ttlDays": body.ttlDays},
    )
    base_url = os.environ.get("CORE_BASE_URL", "http://localhost:8200")
    return ShareLinkCreated(
        url=f"{base_url}/share-links/{token}", expiresAt=link.expires_at.isoformat()
    )


@router.get("/items/{item_id}/share-links", response_model=list[ShareLinkListItem])
def list_share_links_route(
    item_id: str,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> list[ShareLinkListItem]:
    _require_share_access(session, item_id=item_id, user=user)
    links = sharing_repo.list_share_links(session, tenant_id=user.tenant_id, item_id=item_id)
    return [
        ShareLinkListItem(
            id=link.id, expiresAt=link.expires_at.isoformat(), revoked=link.revoked_at is not None
        )
        for link in links
    ]


@router.delete("/items/{item_id}/share-links/{link_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_share_link_route(
    item_id: str,
    link_id: str,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> Response:
    _require_share_access(session, item_id=item_id, user=user)
    ok = sharing_repo.revoke_share_link(session, tenant_id=user.tenant_id, link_id=link_id)
    if not ok:
        raise HTTPException(status_code=404, detail="share link not found")
    write_audit(
        session,
        tenant_id=user.tenant_id,
        actor_id=user.id,
        actor_kind="user",
        action="share_link.revoke",
        object_type="share_link",
        object_id=link_id,
        payload={"itemId": item_id},
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/share-links/{token}", response_model=ResolvedShareLink)
def resolve_share_link_route(
    token: str,
    session: Session = Depends(get_session),
) -> ResolvedShareLink:
    """Résolution PUBLIQUE (aucune dépendance get_current_user) : le jeton
    porte à lui seul le droit d'accès à cet item précis, en lecture seule.
    401 (jamais 500) sur un jeton invalide, expiré, ou dont la ligne
    share_link a été révoquée entre-temps — même discipline que
    decode_export_token vis-à-vis d'une instance sans secret configuré."""
    try:
        claims = decode_share_link_token(token)
    except ShareLinkTokenError:
        raise HTTPException(status_code=401, detail="invalid or expired share link") from None
    link = sharing_repo.get_active_share_link(
        session, tenant_id=claims.tenant_id, link_id=claims.share_link_id
    )
    if link is None:
        raise HTTPException(status_code=401, detail="invalid or expired share link")
    item = repo.get_item(
        session, tenant_id=claims.tenant_id, item_id=claims.item_id, current_user_id=None
    )
    if item is None:
        raise HTTPException(status_code=401, detail="invalid or expired share link")
    write_audit(
        session,
        tenant_id=claims.tenant_id,
        actor_id=None,
        actor_kind="anonymous",
        action="share_link.access",
        object_type="share_link",
        object_id=link.id,
        payload={"itemId": claims.item_id},
    )
    return ResolvedShareLink(
        itemId=item.pk,
        title=item.title,
        resourceType=item.resourceType,
        expiresAt=link.expires_at.isoformat(),
    )
