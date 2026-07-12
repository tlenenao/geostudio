"""Routes OGC API Features (Part 1 lecture, Part 4 écriture).
Le repository et le scope RLS sont injectables : les tests SQLite substituent
un fake et un scope nul ; le vrai chemin est PostGIS-only."""
from contextlib import contextmanager
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.audit.writer import write_audit
from app.auth.dependency import get_current_user, get_current_user_optional
from app.collections.repository import get_access_facts
from app.collections.routes import get_introspector, get_readable_collection
from app.db import get_session
from app.features.repository import FilterError
from app.features.validation import validate_feature
from app.sharing.authorization import can

router = APIRouter()

RESERVED_QUERY_PARAMS = {"limit", "offset", "bbox", "f"}
MAX_LIMIT = 1000

CONFORMANCE_CLASSES = [
    "http://www.opengis.net/spec/ogcapi-features-1/1.0/conf/core",
    "http://www.opengis.net/spec/ogcapi-features-1/1.0/conf/oas30",
    "http://www.opengis.net/spec/ogcapi-features-1/1.0/conf/geojson",
    "http://www.opengis.net/spec/ogcapi-features-4/1.0/conf/create-replace-delete",
]


@router.get("/")
def landing_page(request: Request):
    base = str(request.base_url).rstrip("/")
    return {
        "title": "GeoStudio OGC API Features",
        "description": "Collections éditables du cœur GeoStudio",
        "links": [
            {"rel": "self", "type": "application/json", "href": f"{base}/"},
            {"rel": "conformance", "type": "application/json", "href": f"{base}/conformance"},
            {"rel": "data", "type": "application/json", "href": f"{base}/collections"},
            {"rel": "service-desc", "type": "application/vnd.oai.openapi+json;version=3.0",
             "href": f"{base}/openapi.json"},
        ],
    }


@router.get("/conformance")
def conformance():
    return {"conformsTo": CONFORMANCE_CLASSES}


def get_features_repo():  # overridé en test SQLite
    from app.features import repository
    return repository


@contextmanager
def null_rls_scope(session, tenant_id):  # pour SQLite (pas de rôles/GUC)
    yield


def get_rls_scope():  # overridé en test SQLite
    from app.features.rls import rls_scope
    return rls_scope


def _validation_error(errors: list[dict], status: int = 400):
    return HTTPException(status_code=status, detail={"errors": errors})


def _parse_bbox(raw: str | None):
    if raw is None:
        return None
    parts = raw.split(",")
    try:
        if len(parts) != 4:
            raise ValueError(raw)
        return tuple(float(p) for p in parts)
    except ValueError:
        raise _validation_error(
            [{"field": "bbox", "code": "invalid_bbox",
              "message": "bbox must be minx,miny,maxx,maxy"}])


def _collect_filters(request: Request) -> dict[str, str]:
    return {k: v for k, v in request.query_params.items()
            if k not in RESERVED_QUERY_PARAMS}


def _page_links(request: Request, *, limit: int, offset: int, page) -> list[dict]:
    def href(o: int) -> str:
        return str(request.url.include_query_params(limit=limit, offset=o))

    links = [{"rel": "self", "type": "application/geo+json", "href": str(request.url)}]
    if offset + page.number_returned < page.number_matched:
        links.append({"rel": "next", "type": "application/geo+json",
                      "href": href(offset + limit)})
    if offset > 0:
        links.append({"rel": "prev", "type": "application/geo+json",
                      "href": href(max(0, offset - limit))})
    return links


@router.get("/collections/{collection_id}/items")
def list_features(
    collection_id: str, request: Request,
    limit: int = Query(100, ge=1), offset: int = Query(0, ge=0),
    bbox: str | None = None,
    user=Depends(get_current_user_optional), session: Session = Depends(get_session),
    introspect=Depends(get_introspector), repo=Depends(get_features_repo),
    rls=Depends(get_rls_scope),
):
    col = get_readable_collection(session, user, collection_id)
    info = introspect(session, col.table_name)
    limit = min(limit, MAX_LIMIT)
    parsed_bbox = _parse_bbox(bbox)
    filters = _collect_filters(request)
    try:
        with rls(session, col.tenant_id):
            page = repo.select_features(session, info, limit=limit, offset=offset,
                                        bbox=parsed_bbox, filters=filters or None)
    except FilterError as exc:
        raise _validation_error(
            [{"field": exc.field, "code": "unknown_filter", "message": exc.message}])
    return {
        "type": "FeatureCollection",
        "features": page.features,
        "numberMatched": page.number_matched,
        "numberReturned": page.number_returned,
        "timeStamp": datetime.now(timezone.utc).isoformat(),
        "links": _page_links(request, limit=limit, offset=offset, page=page),
    }


@router.get("/collections/{collection_id}/items/{fid}")
def get_single_feature(
    collection_id: str, fid: str,
    user=Depends(get_current_user_optional), session: Session = Depends(get_session),
    introspect=Depends(get_introspector), repo=Depends(get_features_repo),
    rls=Depends(get_rls_scope),
):
    col = get_readable_collection(session, user, collection_id)
    info = introspect(session, col.table_name)
    with rls(session, col.tenant_id):
        feature = repo.get_feature(session, info, fid=fid)
    if feature is None:
        raise HTTPException(status_code=404, detail="feature not found")
    return feature


def _get_writable(session, user, collection_id):
    col = get_readable_collection(session, user, collection_id)
    if not can(session, user_id=user.id, action="write", item=get_access_facts(col),
               kind="collection", actor_is_admin=user.is_admin):
        raise HTTPException(status_code=403, detail="write access required")
    if not col.editable:
        raise HTTPException(status_code=403, detail="collection is not editable")
    return col


def _validated(introspect, session, col, payload):
    info = introspect(session, col.table_name)
    errors = validate_feature(info, payload)
    if errors:
        raise _validation_error(errors)
    return info


@router.post("/collections/{collection_id}/items", status_code=201)
def create_feature(
    collection_id: str, payload: dict, request: Request, response: Response,
    user=Depends(get_current_user), session: Session = Depends(get_session),
    introspect=Depends(get_introspector), repo=Depends(get_features_repo),
    rls=Depends(get_rls_scope),
):
    col = _get_writable(session, user, collection_id)
    info = _validated(introspect, session, col, payload)
    try:
        with rls(session, col.tenant_id):
            fid = repo.insert_feature(session, info,
                                      properties=payload.get("properties") or {},
                                      geometry=payload.get("geometry"))
    except IntegrityError:
        raise HTTPException(status_code=409, detail="feature conflicts with an existing row")
    session.execute(
        text("UPDATE collections SET feature_count = feature_count + 1 WHERE id = :id"),
        {"id": col.id},
    )
    write_audit(session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="user",
                action="feature.create", object_type="feature", object_id=str(fid),
                payload={"collection": col.id, "fid": str(fid)})
    response.headers["Location"] = str(
        request.url_for("get_single_feature", collection_id=col.id, fid=str(fid)))
    return {"id": fid}


@router.put("/collections/{collection_id}/items/{fid}", status_code=204)
def put_feature(
    collection_id: str, fid: str, payload: dict,
    user=Depends(get_current_user), session: Session = Depends(get_session),
    introspect=Depends(get_introspector), repo=Depends(get_features_repo),
    rls=Depends(get_rls_scope),
):
    col = _get_writable(session, user, collection_id)
    info = _validated(introspect, session, col, payload)
    with rls(session, col.tenant_id):
        ok = repo.replace_feature(session, info, fid=fid,
                                  properties=payload.get("properties") or {},
                                  geometry=payload.get("geometry"))
    if not ok:
        raise HTTPException(status_code=404, detail="feature not found")
    write_audit(session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="user",
                action="feature.update", object_type="feature", object_id=fid,
                payload={"collection": col.id, "fid": fid})


@router.delete("/collections/{collection_id}/items/{fid}", status_code=204)
def remove_feature(
    collection_id: str, fid: str,
    user=Depends(get_current_user), session: Session = Depends(get_session),
    introspect=Depends(get_introspector), repo=Depends(get_features_repo),
    rls=Depends(get_rls_scope),
):
    col = _get_writable(session, user, collection_id)
    info = introspect(session, col.table_name)
    with rls(session, col.tenant_id):
        ok = repo.delete_feature(session, info, fid=fid)
    if not ok:
        raise HTTPException(status_code=404, detail="feature not found")
    session.execute(
        text("UPDATE collections SET feature_count = feature_count - 1 WHERE id = :id"),
        {"id": col.id},
    )
    write_audit(session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="user",
                action="feature.delete", object_type="feature", object_id=fid,
                payload={"collection": col.id, "fid": fid})
