# SPDX-License-Identifier: Apache-2.0
"""Routeur STAC (lecture seule) monté sous /stac. Réutilise le chemin de
requête OGC Features (select_features/get_feature, rls_scope) et les portes de
permission existantes (list_visible_collections, get_readable_collection,
404 non-fuyant). Aucune écriture, aucune surface shell/MCP."""

import base64
import json
from datetime import UTC, datetime
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth.dependency import get_current_user_optional
from app.collections.repository import list_visible_collections
from app.collections.routes import get_introspector, get_readable_collection
from app.db import get_session
from app.features.routes import get_features_repo, get_rls_scope
from app.stac import serializers
from app.stac.extent import estimated_bbox_4326

router = APIRouter(prefix="/stac", tags=["stac"])

MAX_LIMIT = 1000
DEFAULT_LIMIT = 100


def get_bbox_provider():  # overridé en test SQLite (ST_EstimatedExtent absent)
    return estimated_bbox_4326


def _base(request: Request) -> str:
    return str(request.base_url).rstrip("/")


def _rfc3339(dt) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _visible_collections(session: Session, user):
    if user is not None:
        tenant_id = user.tenant_id
    else:
        from app.tenants.repository import get_or_create_default_tenant

        tenant_id = get_or_create_default_tenant(session).id
    cols = list_visible_collections(
        session,
        tenant_id=tenant_id,
        user_id=user.id if user else None,
        is_admin=bool(user and user.is_admin),
    )
    return sorted(cols, key=lambda c: c.id)


@router.get("")
def landing(
    request: Request,
    user=Depends(get_current_user_optional),
    session: Session = Depends(get_session),
):
    cols = _visible_collections(session, user)
    return serializers.catalog(base=_base(request), collection_ids=[c.id for c in cols])


@router.get("/conformance")
def conformance():
    return serializers.conformance()


@router.get("/collections")
def list_collections(
    request: Request,
    user=Depends(get_current_user_optional),
    session: Session = Depends(get_session),
    introspect=Depends(get_introspector),
    bbox_provider=Depends(get_bbox_provider),
    rls=Depends(get_rls_scope),
):
    docs = []
    for col in _visible_collections(session, user):
        info = introspect(session, col.table_name)
        with rls(session, col.tenant_id):
            bbox = bbox_provider(session, info)
        docs.append(
            serializers.collection(
                base=_base(request),
                collection_id=col.id,
                title=col.title,
                description=col.description or "",
                bbox=bbox,
                temporal_start=_rfc3339(col.created_at),
            )
        )
    return {
        "collections": docs,
        "links": [
            {
                "rel": "self",
                "type": "application/json",
                "href": f"{_base(request)}/stac/collections",
            },
            {"rel": "root", "type": "application/json", "href": f"{_base(request)}/stac"},
        ],
    }


@router.get("/collections/{collection_id}")
def get_collection(
    collection_id: str,
    request: Request,
    user=Depends(get_current_user_optional),
    session: Session = Depends(get_session),
    introspect=Depends(get_introspector),
    bbox_provider=Depends(get_bbox_provider),
    rls=Depends(get_rls_scope),
):
    col = get_readable_collection(session, user, collection_id)  # 404 non-fuyant
    info = introspect(session, col.table_name)
    with rls(session, col.tenant_id):
        bbox = bbox_provider(session, info)
    return serializers.collection(
        base=_base(request),
        collection_id=col.id,
        title=col.title,
        description=col.description or "",
        bbox=bbox,
        temporal_start=_rfc3339(col.created_at),
    )


def _parse_bbox(raw: str | None):
    if raw is None:
        return None
    parts = raw.split(",")
    if len(parts) != 4:
        raise HTTPException(status_code=400, detail="bbox must be minx,miny,maxx,maxy")
    try:
        return tuple(float(p) for p in parts)
    except ValueError:
        raise HTTPException(status_code=400, detail="bbox must be minx,miny,maxx,maxy")


@router.get("/collections/{collection_id}/items")
def list_items(
    collection_id: str,
    request: Request,
    limit: int = Query(DEFAULT_LIMIT, ge=1),
    offset: int = Query(0, ge=0),
    bbox: str | None = None,
    user=Depends(get_current_user_optional),
    session: Session = Depends(get_session),
    introspect=Depends(get_introspector),
    repo=Depends(get_features_repo),
    rls=Depends(get_rls_scope),
):
    col = get_readable_collection(session, user, collection_id)
    info = introspect(session, col.table_name)
    limit = min(limit, MAX_LIMIT)
    parsed_bbox = _parse_bbox(bbox)
    with rls(session, col.tenant_id):
        page = repo.select_features(
            session, info, limit=limit, offset=offset, bbox=parsed_bbox, filters=None
        )
    dtv = _rfc3339(col.updated_at)
    base = _base(request)
    items = [
        serializers.item(base=base, collection_id=col.id, feature=f, datetime_value=dtv)
        for f in page.features
    ]
    links = [
        {"rel": "self", "type": "application/geo+json", "href": str(request.url)},
        {"rel": "root", "type": "application/json", "href": f"{base}/stac"},
    ]
    if offset + page.number_returned < page.number_matched:
        links.append(
            {
                "rel": "next",
                "type": "application/geo+json",
                "href": str(request.url.include_query_params(limit=limit, offset=offset + limit)),
            }
        )
    return serializers.item_collection(items=items, links=links)


@router.get("/collections/{collection_id}/items/{feature_id}")
def get_item(
    collection_id: str,
    feature_id: str,
    request: Request,
    user=Depends(get_current_user_optional),
    session: Session = Depends(get_session),
    introspect=Depends(get_introspector),
    repo=Depends(get_features_repo),
    rls=Depends(get_rls_scope),
):
    col = get_readable_collection(session, user, collection_id)
    info = introspect(session, col.table_name)
    with rls(session, col.tenant_id):
        feature = repo.get_feature(session, info, fid=feature_id)
    if feature is None:
        raise HTTPException(status_code=404, detail="item not found")
    return serializers.item(
        base=_base(request),
        collection_id=col.id,
        feature=feature,
        datetime_value=_rfc3339(col.updated_at),
    )


class SearchBody(BaseModel):
    bbox: list[float] | None = None
    datetime: str | None = None
    collections: list[str] | None = None
    ids: list[str] | None = None
    limit: int = Field(DEFAULT_LIMIT, ge=1)
    token: str | None = None


def _encode_token(collection_id: str, offset: int) -> str:
    raw = json.dumps({"c": collection_id, "o": offset}).encode()
    return base64.urlsafe_b64encode(raw).decode()


def _decode_token(token: str | None):
    if not token:
        return None
    try:
        d = json.loads(base64.urlsafe_b64decode(token.encode()))
        return str(d["c"]), int(d["o"])
    except Exception:
        return None


def _parse_dt(value: str):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _collection_in_datetime(updated_at, datetime_param: str | None) -> bool:
    if not datetime_param:
        return True
    ua = updated_at if updated_at.tzinfo else updated_at.replace(tzinfo=UTC)
    if "/" in datetime_param:
        start_s, end_s = datetime_param.split("/", 1)
        if start_s not in ("", "..") and ua < _parse_dt(start_s):
            return False
        if end_s not in ("", "..") and ua > _parse_dt(end_s):
            return False
        return True
    return ua == _parse_dt(datetime_param)


def _run_search(
    request,
    session,
    user,
    *,
    bbox,
    datetime_param,
    collections,
    ids,
    limit,
    token,
    introspect,
    repo,
    rls,
):
    limit = min(limit, MAX_LIMIT)
    cols = _visible_collections(session, user)
    if collections:
        wanted = set(collections)
        cols = [c for c in cols if c.id in wanted]
    cols = [c for c in cols if _collection_in_datetime(c.updated_at, datetime_param)]

    decoded = _decode_token(token)
    start_c, start_o = decoded if decoded else (None, 0)
    started = start_c is None
    base = _base(request)
    results, next_token = [], None

    for col in cols:
        if not started:
            if col.id != start_c:
                continue
            started = True
            offset = start_o
        else:
            offset = 0
        info = introspect(session, col.table_name)
        remaining = limit - len(results)
        with rls(session, col.tenant_id):
            page = repo.select_features(
                session, info, limit=remaining, offset=offset, bbox=bbox, filters=None
            )
        dtv = _rfc3339(col.updated_at)
        for f in page.features:
            if ids and str(f["id"]) not in ids:
                continue
            results.append(
                serializers.item(base=base, collection_id=col.id, feature=f, datetime_value=dtv)
            )
        consumed = offset + page.number_returned
        if len(results) >= limit and consumed < page.number_matched:
            next_token = _encode_token(col.id, consumed)
            break

    links = [
        {"rel": "self", "type": "application/geo+json", "href": str(request.url)},
        {"rel": "root", "type": "application/json", "href": f"{base}/stac"},
    ]
    if next_token:
        params = {"token": next_token, "limit": limit}
        if collections:
            params["collections"] = ",".join(collections)
        if bbox:
            params["bbox"] = ",".join(str(x) for x in bbox)
        if datetime_param:
            params["datetime"] = datetime_param
        if ids:
            params["ids"] = ",".join(ids)
        href = f"{base}/stac/search?{urlencode(params)}"
        links.append({"rel": "next", "type": "application/geo+json", "href": href})
    return serializers.item_collection(items=results, links=links)


@router.get("/search")
def search_get(
    request: Request,
    bbox: str | None = None,
    datetime: str | None = None,
    collections: str | None = None,
    ids: str | None = None,
    limit: int = Query(DEFAULT_LIMIT, ge=1),
    token: str | None = None,
    user=Depends(get_current_user_optional),
    session: Session = Depends(get_session),
    introspect=Depends(get_introspector),
    repo=Depends(get_features_repo),
    rls=Depends(get_rls_scope),
):
    return _run_search(
        request,
        session,
        user,
        bbox=_parse_bbox(bbox),
        datetime_param=datetime,
        collections=collections.split(",") if collections else None,
        ids=ids.split(",") if ids else None,
        limit=limit,
        token=token,
        introspect=introspect,
        repo=repo,
        rls=rls,
    )


@router.post("/search")
def search_post(
    request: Request,
    body: SearchBody,
    user=Depends(get_current_user_optional),
    session: Session = Depends(get_session),
    introspect=Depends(get_introspector),
    repo=Depends(get_features_repo),
    rls=Depends(get_rls_scope),
):
    if body.bbox is not None and len(body.bbox) != 4:
        raise HTTPException(status_code=400, detail="bbox must be minx,miny,maxx,maxy")
    return _run_search(
        request,
        session,
        user,
        bbox=tuple(body.bbox) if body.bbox else None,
        datetime_param=body.datetime,
        collections=body.collections,
        ids=body.ids,
        limit=body.limit,
        token=body.token,
        introspect=introspect,
        repo=repo,
        rls=rls,
    )
