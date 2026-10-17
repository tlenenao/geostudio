# SPDX-License-Identifier: Apache-2.0
"""OGC API Records Part 1 (AUD-048, D11) sur le catalogue d'items + fiche ISO 19139 par
collection. Aucun accès SQL propre : liste/détail passent par les mêmes fonctions que
/items (authentifié, can()) et /public/items (anonyme : publié seulement)."""

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.auth.dependency import get_current_user_optional
from app.bbox import parse_bbox_floats
from app.collections.introspection import TableNotFound, UnsupportedTable
from app.collections.routes import get_introspector, get_readable_collection
from app.db import get_session
from app.dcat.routes import _resolve_bbox_degrading, _resolve_tenant, get_bbox_provider
from app.features.routes import get_rls_scope
from app.items import repository as items_repo
from app.items.service import get_item_service
from app.records import iso19139, serializers
from app.roles.guards import has_privilege
from app.roles.privileges import Privilege
from app.tenants.repository import DEFAULT_TENANT_SLUG

# Un seul routeur nommé `router`, sans préfixe : l'index AST du bilan de fonctionnalités
# (scripts/feature_health/rest_surface.py) ne voit que les décorateurs `@router.*`.
router = APIRouter(tags=["records"])
GEOJSON = "application/geo+json"


def _base(request: Request) -> str:
    return str(request.base_url).rstrip("/") + "/v1"


def _check_catalog(catalog_id: str) -> None:
    if catalog_id != serializers.CATALOG_ID:
        raise HTTPException(status_code=404, detail="unknown catalog")


@router.get("/records")
def landing(request: Request):
    b = _base(request)
    return {
        "title": "GeoStudio OGC API Records",
        "links": [
            {"rel": "self", "type": "application/json", "href": f"{b}/records"},
            {"rel": "conformance", "type": "application/json", "href": f"{b}/records/conformance"},
            {"rel": "data", "type": "application/json", "href": f"{b}/records/collections"},
        ],
    }


@router.get("/records/conformance")
def conformance():
    return {"conformsTo": serializers.CONFORMANCE}


@router.get("/records/collections")
def collections(request: Request):
    b = _base(request)
    return {
        "collections": [serializers.catalog(base=b)],
        "links": [{"rel": "self", "type": "application/json", "href": f"{b}/records/collections"}],
    }


@router.get("/records/collections/{catalog_id}")
def get_catalog(catalog_id: str, request: Request):
    _check_catalog(catalog_id)
    return JSONResponse(
        serializers.catalog(base=_base(request)), media_type="application/ogc-catalog+json"
    )


@router.get("/records/collections/{catalog_id}/items")
def list_records(
    catalog_id: str,
    request: Request,
    q: str | None = None,
    bbox: str | None = None,
    type: str | None = None,
    limit: int = Query(10, ge=1, le=100),
    page: int = Query(1, ge=1),
    user=Depends(get_current_user_optional),
    session: Session = Depends(get_session, scope="function"),
):
    _check_catalog(catalog_id)
    try:
        box = parse_bbox_floats(bbox)  # None si absent
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"invalid bbox: {exc}") from exc
    if user is None:
        result = items_repo.list_published_items(
            session,
            tenant_id=DEFAULT_TENANT_SLUG,
            resource_type=type,
            q=q,
            bbox=box,
            page=page,
            page_size=limit,
        )
    else:
        # Revue L6 M2 : même périmètre de kinds que l'anonyme (pas de pipeline/alerte/rapport).
        kinds = items_repo.PUBLIC_KINDS
        result = items_repo.list_items(
            session,
            tenant_id=user.tenant_id,
            current_user_id=user.id,
            q=q,
            resource_type=((type,) if type in kinds else ()) if type else kinds,
            scope="all",
            page=page,
            page_size=limit,
            bbox=box,
        )
    b = _base(request)
    links = [{"rel": "self", "type": GEOJSON, "href": str(request.url)}]
    if page * limit < result.total:
        links.append(
            {
                "rel": "next",
                "type": GEOJSON,
                "href": str(request.url.include_query_params(page=page + 1, limit=limit)),
            }
        )
    body = {
        "type": "FeatureCollection",
        "features": [serializers.record(base=b, item=i) for i in result.items],
        "numberMatched": result.total,
        "numberReturned": len(result.items),
        "links": links,
    }
    return JSONResponse(body, media_type=GEOJSON)


@router.get("/records/collections/{catalog_id}/items/{record_id}")
def get_record(
    catalog_id: str,
    record_id: str,
    request: Request,
    user=Depends(get_current_user_optional),
    session: Session = Depends(get_session, scope="function"),
):
    _check_catalog(catalog_id)
    if user is None:
        item = items_repo.get_published_item(
            session, item_id=record_id, tenant_id=DEFAULT_TENANT_SLUG
        )
        if item is None or item.contentStatus == "deprecated":
            raise HTTPException(status_code=404, detail="record not found")
    else:
        item = get_item_service(session, item_id=record_id, user=user)
        if item.resourceType not in items_repo.PUBLIC_KINDS:
            raise HTTPException(status_code=404, detail="record not found")
    return JSONResponse(serializers.record(base=_base(request), item=item), media_type=GEOJSON)


@router.get("/collections/{collection_id}/metadata")
def get_iso_metadata(
    collection_id: str,
    request: Request,
    user=Depends(get_current_user_optional),
    session: Session = Depends(get_session, scope="function"),
    introspect=Depends(get_introspector),
    bbox_provider=Depends(get_bbox_provider),
    rls=Depends(get_rls_scope),
) -> Response:
    col = get_readable_collection(
        session,
        user,
        collection_id,
        can_manage_collections=bool(
            user and has_privilege(session, user, Privilege.ADMIN_COLLECTIONS_MANAGE.value)
        ),
    )  # 404 non-fuyant, même porte que DCAT
    # Revue L6 M1 : avant l'introspection — une DBAPIError y avorte la transaction
    # Postgres et toute requête suivante échouerait (même ordre que DCAT get_dataset).
    publisher = _resolve_tenant(session, user).name
    try:
        srid = introspect(session, col.table_name).srid
    except (TableNotFound, UnsupportedTable, DBAPIError):
        srid = None
    bbox = _resolve_bbox_degrading(
        session, col, introspect=introspect, bbox_provider=bbox_provider, rls=rls
    )
    xml = iso19139.collection_metadata(
        col=col,
        bbox=bbox,
        srid=srid,
        items_url=f"{_base(request)}/collections/{col.id}/items",
        publisher=publisher,
    )
    return Response(xml, media_type="application/xml")
