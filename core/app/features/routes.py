"""Routes OGC API Features (Part 1 lecture ; Part 4 écriture en task 9).
Le repository et le scope RLS sont injectables : les tests SQLite substituent
un fake et un scope nul ; le vrai chemin est PostGIS-only."""
from contextlib import contextmanager
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.auth.dependency import get_current_user_optional
from app.collections.routes import get_introspector, get_readable_collection
from app.db import get_session
from app.features.repository import FilterError

router = APIRouter()

RESERVED_QUERY_PARAMS = {"limit", "offset", "bbox", "f"}
MAX_LIMIT = 1000


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
