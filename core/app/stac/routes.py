# SPDX-License-Identifier: Apache-2.0
"""Routeur STAC (lecture seule) monté sous /stac. Réutilise le chemin de
requête OGC Features (select_features/get_feature, rls_scope) et les portes de
permission existantes (list_visible_collections, get_readable_collection,
404 non-fuyant). Aucune écriture, aucune surface shell/MCP."""

import base64
import json
import logging
from datetime import UTC, datetime
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.auth.dependency import get_current_user_optional
from app.collections.introspection import TableNotFound, UnsupportedTable, hide_sensitive_columns
from app.collections.repository import list_visible_collections
from app.collections.routes import get_introspector, get_readable_collection
from app.db import get_session
from app.features.routes import get_features_repo, get_masked_for_user, get_rls_scope
from app.roles.guards import has_privilege
from app.roles.privileges import Privilege
from app.stac import serializers
from app.stac.extent import rls_scoped_bbox_4326

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/stac", tags=["stac"])


class GeoJSONResponse(JSONResponse):
    """stac-api-validator (REV-098/GAP-04) exige application/geo+json — pas le
    application/json que FastAPI applique par défaut à un dict — sur toute
    réponse FeatureCollection/Feature (Features + Item Search conformance
    classes)."""

    media_type = "application/geo+json"


MAX_LIMIT = 1000
DEFAULT_LIMIT = 100


def get_bbox_provider():  # overridé en test SQLite (ST_EstimatedExtent absent)
    return rls_scoped_bbox_4326


def _base(request: Request) -> str:
    # request.base_url ne porte jamais /v1 (juste scheme://host/) — ce
    # routeur est nesté sous /v1 (SP-57b), l'ajouter explicitement.
    return str(request.base_url).rstrip("/") + "/v1"


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
        can_see_all=bool(
            user and has_privilege(session, user, Privilege.ADMIN_COLLECTIONS_MANAGE.value)
        ),
    )
    return sorted(cols, key=lambda c: c.id)


def _collection_doc(request: Request, col, bbox) -> dict:
    return serializers.collection(
        base=_base(request),
        collection_id=col.id,
        title=col.title,
        description=col.description or "",
        bbox=bbox,
        temporal_start=(
            f"{col.temporal_start.isoformat()}T00:00:00Z"
            if col.temporal_start
            else _rfc3339(col.created_at)
        ),
        temporal_end=(f"{col.temporal_end.isoformat()}T23:59:59Z" if col.temporal_end else None),
        license=col.license,
        license_uri=col.license_uri,
        providers=[{"name": col.producer, "roles": ["producer"]}] if col.producer else None,
    )


def _item_datetimes(col) -> tuple[str, str | None]:
    """(datetime, end_datetime) d'un item : emprise temporelle déclarée de la
    collection si renseignée, sinon sa date de mise à jour (j07-011)."""
    if col.temporal_start:
        end = f"{col.temporal_end.isoformat()}T23:59:59Z" if col.temporal_end else None
        return f"{col.temporal_start.isoformat()}T00:00:00Z", end
    return _rfc3339(col.updated_at), None


@router.get("")
def landing(
    request: Request,
    user=Depends(get_current_user_optional),
    session: Session = Depends(get_session, scope="function"),
):
    cols = _visible_collections(session, user)
    root = str(request.base_url).rstrip("/")
    return serializers.catalog(base=_base(request), root=root, collection_ids=[c.id for c in cols])


@router.get("/conformance")
def conformance():
    return serializers.conformance()


@router.get("/collections")
def list_collections(
    request: Request,
    limit: int = Query(DEFAULT_LIMIT, ge=1),
    offset: int = Query(0, ge=0),
    user=Depends(get_current_user_optional),
    session: Session = Depends(get_session, scope="function"),
    introspect=Depends(get_introspector),
    bbox_provider=Depends(get_bbox_provider),
    rls=Depends(get_rls_scope),
):
    limit = min(limit, MAX_LIMIT)
    cols = _visible_collections(session, user)
    total = len(cols)
    cols_page = cols[offset : offset + limit]
    docs = []
    for col in cols_page:
        try:
            info = introspect(session, col.table_name)
            with rls(session, col.tenant_id):
                bbox = bbox_provider(session, info)
        except (TableNotFound, UnsupportedTable, DBAPIError) as exc:
            logger.warning("stac catalog: extent lookup failed for collection %s: %s", col.id, exc)
            bbox = None
        docs.append(_collection_doc(request, col, bbox))
    links = [
        {
            "rel": "self",
            "type": "application/json",
            "href": f"{_base(request)}/stac/collections",
        },
        {"rel": "root", "type": "application/json", "href": f"{_base(request)}/stac"},
    ]
    if offset + len(cols_page) < total:
        links.append(
            {
                "rel": "next",
                "type": "application/json",
                "href": str(request.url.include_query_params(limit=limit, offset=offset + limit)),
            }
        )
    return {
        "collections": docs,
        "links": links,
    }


@router.get("/collections/{collection_id}")
def get_collection(
    collection_id: str,
    request: Request,
    user=Depends(get_current_user_optional),
    session: Session = Depends(get_session, scope="function"),
    introspect=Depends(get_introspector),
    bbox_provider=Depends(get_bbox_provider),
    rls=Depends(get_rls_scope),
):
    col = get_readable_collection(
        session,
        user,
        collection_id,
        can_manage_collections=bool(
            user and has_privilege(session, user, Privilege.ADMIN_COLLECTIONS_MANAGE.value)
        ),
    )  # 404 non-fuyant
    try:
        info = introspect(session, col.table_name)
        with rls(session, col.tenant_id):
            bbox = bbox_provider(session, info)
    except (TableNotFound, UnsupportedTable, DBAPIError) as exc:
        logger.warning("stac collection %s: extent lookup failed: %s", col.id, exc)
        bbox = None  # j07-009 : dégradation gracieuse, comme /stac/collections
    return _collection_doc(request, col, bbox)


def _parse_bbox(raw: str | None):
    if raw is None:
        return None
    parts = raw.split(",")
    if len(parts) != 4:
        raise HTTPException(status_code=400, detail="bbox must be minx,miny,maxx,maxy")
    try:
        return tuple(float(p) for p in parts)
    except ValueError:
        raise HTTPException(status_code=400, detail="bbox must be minx,miny,maxx,maxy") from None


@router.get("/collections/{collection_id}/items", response_class=GeoJSONResponse)
def list_items(
    collection_id: str,
    request: Request,
    limit: int = Query(DEFAULT_LIMIT, ge=1),
    offset: int = Query(0, ge=0),
    bbox: str | None = None,
    user=Depends(get_current_user_optional),
    session: Session = Depends(get_session, scope="function"),
    introspect=Depends(get_introspector),
    repo=Depends(get_features_repo),
    rls=Depends(get_rls_scope),
    masked=Depends(get_masked_for_user),
):
    col = get_readable_collection(
        session,
        user,
        collection_id,
        can_manage_collections=bool(
            user and has_privilege(session, user, Privilege.ADMIN_COLLECTIONS_MANAGE.value)
        ),
    )
    info = introspect(session, col.table_name)
    if masked:
        info = hide_sensitive_columns(info, col.sensitive_fields)
    limit = min(limit, MAX_LIMIT)
    parsed_bbox = _parse_bbox(bbox)
    with rls(session, col.tenant_id, masked=masked):
        page = repo.select_features(
            session, info, limit=limit, offset=offset, bbox=parsed_bbox, filters=None
        )
    dtv, dte = _item_datetimes(col)
    base = _base(request)
    items = [
        serializers.item(
            base=base, collection_id=col.id, feature=f, datetime_value=dtv, end_datetime=dte
        )
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


@router.get("/collections/{collection_id}/items/{feature_id}", response_class=GeoJSONResponse)
def get_item(
    collection_id: str,
    feature_id: str,
    request: Request,
    user=Depends(get_current_user_optional),
    session: Session = Depends(get_session, scope="function"),
    introspect=Depends(get_introspector),
    repo=Depends(get_features_repo),
    rls=Depends(get_rls_scope),
    masked=Depends(get_masked_for_user),
):
    col = get_readable_collection(
        session,
        user,
        collection_id,
        can_manage_collections=bool(
            user and has_privilege(session, user, Privilege.ADMIN_COLLECTIONS_MANAGE.value)
        ),
    )
    info = introspect(session, col.table_name)
    if masked:
        info = hide_sensitive_columns(info, col.sensitive_fields)
    with rls(session, col.tenant_id, masked=masked):
        feature = repo.get_feature(session, info, fid=feature_id)
    if feature is None:
        raise HTTPException(status_code=404, detail="item not found")
    return serializers.item(
        base=_base(request),
        collection_id=col.id,
        feature=feature,
        datetime_value=_item_datetimes(col)[0],
        end_datetime=_item_datetimes(col)[1],
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
        raise HTTPException(status_code=400, detail="invalid pagination token") from None


def _parse_dt(value: str):
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(
            status_code=400, detail="datetime must be an RFC 3339 instant or interval"
        ) from None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _parse_datetime_param(datetime_param: str | None):
    """-> (start, end) ; None = borne ouverte. Lève 400 si invalide."""
    if not datetime_param:
        return None
    if "/" in datetime_param:
        start_s, end_s = datetime_param.split("/", 1)
        return (
            None if start_s in ("", "..") else _parse_dt(start_s),
            None if end_s in ("", "..") else _parse_dt(end_s),
        )
    instant = _parse_dt(datetime_param)
    return instant, instant


def _collection_in_datetime(col, window) -> bool:
    """Recouvrement entre la fenêtre demandée et l'emprise temporelle de la
    collection (temporal_start/end si déclarée, sinon l'instant updated_at)."""
    if window is None:
        return True
    if col.temporal_start:
        cs = datetime.combine(col.temporal_start, datetime.min.time(), UTC)
        ce = (
            datetime.combine(col.temporal_end, datetime.max.time(), UTC)
            if col.temporal_end
            else None
        )
    else:
        cs = ce = col.updated_at if col.updated_at.tzinfo else col.updated_at.replace(tzinfo=UTC)
    qs, qe = window
    return (qe is None or cs <= qe) and (qs is None or ce is None or ce >= qs)


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
    masked,
):
    limit = min(limit, MAX_LIMIT)
    cols = _visible_collections(session, user)
    if collections:
        wanted = set(collections)
        cols = [c for c in cols if c.id in wanted]
    window = _parse_datetime_param(datetime_param)
    cols = [c for c in cols if _collection_in_datetime(c, window)]

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
        try:
            info = introspect(session, col.table_name)
        except (TableNotFound, UnsupportedTable) as exc:
            # j07-008 : une collection cassée ne fait pas échouer toute la recherche.
            logger.warning("stac search: collection %s ignorée: %s", col.id, exc)
            continue
        if masked:
            info = hide_sensitive_columns(info, col.sensitive_fields)
        remaining = limit - len(results)
        with rls(session, col.tenant_id, masked=masked):
            page = repo.select_features(
                session, info, limit=remaining, offset=offset, bbox=bbox, filters=None
            )
        dtv, dte = _item_datetimes(col)
        for f in page.features:
            if ids and str(f["id"]) not in ids:
                continue
            results.append(
                serializers.item(
                    base=base, collection_id=col.id, feature=f, datetime_value=dtv, end_datetime=dte
                )
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


@router.get("/search", response_class=GeoJSONResponse)
def search_get(
    request: Request,
    bbox: str | None = None,
    datetime: str | None = None,
    collections: str | None = None,
    ids: str | None = None,
    limit: int = Query(DEFAULT_LIMIT, ge=1),
    token: str | None = None,
    user=Depends(get_current_user_optional),
    session: Session = Depends(get_session, scope="function"),
    introspect=Depends(get_introspector),
    repo=Depends(get_features_repo),
    rls=Depends(get_rls_scope),
    masked=Depends(get_masked_for_user),
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
        masked=masked,
    )


@router.post("/search", response_class=GeoJSONResponse)
def search_post(
    request: Request,
    body: SearchBody,
    user=Depends(get_current_user_optional),
    session: Session = Depends(get_session, scope="function"),
    introspect=Depends(get_introspector),
    repo=Depends(get_features_repo),
    rls=Depends(get_rls_scope),
    masked=Depends(get_masked_for_user),
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
        masked=masked,
    )
