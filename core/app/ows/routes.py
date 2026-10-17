# SPDX-License-Identifier: Apache-2.0
"""WFS 2.0 (lecture) + OGC API Tiles (ARC-11, ADR 0018).

Aucun accès SQL propre : tout passe par la porte de lecture des Features —
`get_collection_for_read` (404 avant 403), `rls_scope` (tenant + limites
géographiques), masquage GAP-22 (`hide_sensitive_columns`) et
`features.repository.select_features`. Montées seulement si CORE_OWS_ENABLED ;
exposition par collection (`Collection.ows_enabled`, faux par défaut)."""

import json
import math
import os
from datetime import UTC, datetime
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.auth.dependency import get_current_user_optional
from app.collections.introspection import hide_sensitive_columns
from app.collections.repository import list_visible_collections
from app.collections.routes import get_collection_for_read, get_introspector
from app.collections.sensitive import unmask_for_owner
from app.configs.guest_access import GuestActor, get_share_link_actor
from app.db import get_session
from app.features.repository import CursorError, FilterError
from app.features.routes import (
    MAX_LIMIT,
    get_features_repo,
    get_masked_for_user,
    get_rls_scope,
    parse_bbox,
    parse_crs,
)
from app.features.tiles import apply_tile_statement_timeout, get_collection_tile
from app.ows import wfs, wms
from app.roles.guards import has_privilege
from app.roles.privileges import Privilege

router = APIRouter()
TMS = "WebMercatorQuad"
TMS_URI = "http://www.opengis.net/def/tilematrixset/OGC/1.0/WebMercatorQuad"
XML = "text/xml; charset=utf-8"
# AUD-155 : GetFeature anonyme (count exact de `hits`, filtre CQL) borné comme le rendu WMS.
STATEMENT_TIMEOUT_MS = 5000


def is_ows_enabled() -> bool:
    """CORE_OWS_ENABLED — capacité instance-wide optionnelle, lue à chaque appel
    (même convention que is_tileset3d_enabled). Faux : aucune route montée."""
    return os.environ.get("CORE_OWS_ENABLED", "false").lower() == "true"


class _OwsError(Exception):
    def __init__(self, status: int, code: str, locator: str | None, message: str):
        self.status, self.code, self.locator, self.message = status, code, locator, message


def _bad(locator: str, message: str, code: str = "InvalidParameterValue") -> _OwsError:
    return _OwsError(400, code, locator, message)


def _readable(session, user, guest, cid: str, locator: str):
    """Collection lisible ET exposée ; sinon 404 (même statut que l'API Features
    pour une collection invisible, pour ne rien révéler de son existence)."""
    if not wfs.NCNAME.match(cid):
        raise _OwsError(404, "InvalidParameterValue", locator, "unknown feature type")
    try:
        col = get_collection_for_read(session, user, cid, guest=guest)
    except HTTPException as exc:
        raise _OwsError(exc.status_code, "InvalidParameterValue", locator, str(exc.detail)) from exc
    if not col.ows_enabled:
        raise _OwsError(404, "InvalidParameterValue", locator, "feature type not exposed")
    return col


def _type_name(q: dict[str, str]) -> list[str]:
    raw = q.get("typenames") or q.get("typename")
    if not raw:
        raise _bad("typeNames", "typeNames is required", "MissingParameterValue")
    names = [n.strip().removeprefix("gs:") for n in raw.split(",") if n.strip()]
    if not names:
        raise _bad("typeNames", "typeNames is required", "MissingParameterValue")
    return names


def _int(q: dict[str, str], key: str, default: int, lo: int) -> int:
    try:
        v = int(q.get(key, default))
    except ValueError:
        raise _bad(key, f"{key} must be an integer") from None
    if v < lo:
        raise _bad(key, f"{key} must be >= {lo}")
    return v


def _bbox(raw: str):
    """`minx,miny,maxx,maxy[,crs]` -> (bbox, srid). WFS 2.0 : un CRS donné en
    urn/EPSG:4326 est en ordre lat,lon ; sans CRS, c'est le CRS par défaut (4326)."""
    parts = raw.split(",")
    crs = None
    if len(parts) == 5:
        crs, parts = parts[4], parts[:4]
    if len(parts) != 4:
        raise _bad("bbox", "bbox must be minx,miny,maxx,maxy[,crs]")
    try:
        v = [float(p) for p in parts]
    except ValueError:
        raise _bad("bbox", "bbox must be numeric") from None
    if not all(math.isfinite(n) for n in v):
        raise _bad("bbox", "bbox must be finite")
    srid = parse_crs(crs, "bbox") or 4326
    if srid == 4326:
        v = [v[1], v[0], v[3], v[2]]  # lat,lon -> lon,lat
    return parse_bbox(",".join(map(str, v)), check_bounds=srid == 4326), srid


def _next_url(request: Request, startindex: int, count: int) -> str:
    kept = [
        (k, v)
        for k, v in request.query_params.multi_items()
        if k.lower() not in ("startindex", "count")
    ]
    kept += [("startindex", str(startindex)), ("count", str(count))]
    return f"{str(request.url).split('?')[0]}?{urlencode(kept)}"


def _xml(body: str, status: int = 200, media: str = XML) -> Response:
    return Response(content=body, status_code=status, media_type=media)


@router.get("/ows/wfs")
def wfs_endpoint(
    request: Request,
    user=Depends(get_current_user_optional),
    guest: GuestActor | None = Depends(get_share_link_actor),
    session: Session = Depends(get_session, scope="function"),
    introspect=Depends(get_introspector),
    repo=Depends(get_features_repo),
    rls=Depends(get_rls_scope),
    masked=Depends(get_masked_for_user),
) -> Response:
    q = {k.lower(): v for k, v in request.query_params.items()}
    try:
        if q.get("service", "WFS").upper() != "WFS":
            raise _bad("service", "only service=WFS is served here")
        version = q.get("version")
        if version and not version.startswith("2.0"):
            raise _bad("version", "only WFS 2.0.x is supported", "VersionNegotiationFailed")
        op = (q.get("request") or "").lower()
        if op == "getcapabilities":
            return _capabilities(request, session, user)
        if op == "describefeaturetype":
            return _describe(q, session, user, guest, introspect, masked)
        if op == "getfeature":
            return _get_feature(request, q, session, user, guest, introspect, repo, rls, masked)
        raise _OwsError(
            400,
            "OperationNotSupported" if op else "MissingParameterValue",
            "request",
            "supported operations: GetCapabilities, DescribeFeatureType, GetFeature",
        )
    except _OwsError as e:
        return _xml(wfs.exception_report(e.code, e.locator, e.message), e.status)
    except HTTPException as e:  # erreurs de validation partagées avec l'API Features
        return _xml(
            wfs.exception_report("InvalidParameterValue", None, str(e.detail)), e.status_code
        )
    except (FilterError, CursorError) as e:
        return _xml(wfs.exception_report("InvalidParameterValue", "filter", str(e)), 400)


def _capabilities(request: Request, session, user) -> Response:
    from app.tenants.repository import get_or_create_default_tenant

    # Même résolution que GET /collections (anonyme : tenant par défaut).
    tenant_id = user.tenant_id if user else get_or_create_default_tenant(session).id
    can_all = bool(user and has_privilege(session, user, Privilege.ADMIN_COLLECTIONS_MANAGE.value))
    cols = list_visible_collections(
        session, tenant_id=tenant_id, user_id=user.id if user else None, can_see_all=can_all
    )
    cols = [c for c in cols if c.ows_enabled and c.geometry_column and wfs.NCNAME.match(c.id)]
    base = f"{str(request.base_url).rstrip('/')}/v1/ows/wfs"
    return _xml(wfs.capabilities(base, "GeoStudio WFS", cols), media="application/xml")


def _describe(q, session, user, guest, introspect, masked) -> Response:
    items = []
    for name in _type_name(q):
        col = _readable(session, user, guest, name, "typeNames")
        info = introspect(session, col.table_name)
        if unmask_for_owner(masked, user, col):
            info = hide_sensitive_columns(info, col.sensitive_fields)
        items.append((col.id, info))
    return _xml(wfs.describe_feature_type(items), media="application/xml")


def _get_feature(request, q, session, user, guest, introspect, repo, rls, masked) -> Response:
    names = _type_name(q)
    if len(names) != 1:
        raise _bad("typeNames", "exactly one feature type per GetFeature is supported")
    col = _readable(session, user, guest, names[0], "typeNames")
    masked = unmask_for_owner(masked, user, col)
    info = introspect(session, col.table_name)
    if masked:
        info = hide_sensitive_columns(info, col.sensitive_fields)
    fmt = (q.get("outputformat") or wfs.GML_FORMAT).strip().lower()
    as_json = fmt in wfs.JSON_ALIASES
    if not as_json and fmt not in {a.lower() for a in wfs.GML_ALIASES}:
        raise _bad("outputFormat", f"unsupported outputFormat '{fmt}'")
    count = min(_int(q, "count", _int(q, "maxfeatures", 1000, 0), 0), MAX_LIMIT)
    start = _int(q, "startindex", 0, 0)
    srid = parse_crs(q.get("srsname"), "srsName") or 4326
    kwargs: dict = {}
    if q.get("bbox"):
        kwargs["bbox"], bbox_srid = _bbox(q["bbox"])
        if bbox_srid != 4326:
            kwargs["bbox_srid"] = bbox_srid
    if q.get("cql_filter"):
        kwargs["cql2"] = q["cql_filter"]
    if srid != 4326:
        kwargs["out_srid"] = srid
    hits = q.get("resulttype", "results").lower() == "hits"
    with rls(session, col.tenant_id, masked=masked):
        apply_tile_statement_timeout(session, STATEMENT_TIMEOUT_MS)
        try:
            page = repo.select_features(
                session,
                info,
                limit=1 if hits else max(count, 1),
                offset=0 if hits else start,
                count_mode="exact" if hits else "capped",
                **kwargs,
            )
        except DBAPIError as exc:
            if getattr(exc.orig, "sqlstate", None) == "57014":  # query_canceled
                raise _OwsError(503, "NoApplicableCode", None, "query timed out") from exc
            raise
    features = [] if hits or count == 0 else page.features
    matched = "unknown" if page.number_matched_lower_bound else page.number_matched
    more = (page.next_cursor is not None or page.next_offset is not None) and not hits and count
    if as_json:
        body = {
            "type": "FeatureCollection",
            "features": features,
            "numberMatched": matched,
            "numberReturned": len(features),
            "timeStamp": datetime.now(UTC).isoformat(),
        }
        return Response(
            content=json.dumps(body, default=str),
            media_type="application/json",
        )
    xml = wfs.feature_collection(
        cid=col.id,
        info=info,
        features=features,
        matched=matched,
        returned=len(features),
        timestamp=datetime.now(UTC).isoformat(),
        srs=f"urn:ogc:def:crs:EPSG::{srid}",
        swap=srid == 4326,
        next_url=_next_url(request, start + count, count) if more else None,
    )
    return _xml(xml, media="application/gml+xml; version=3.2")


# --- OGC API Tiles ---------------------------------------------------------


def _tileset(request: Request, col) -> dict:
    base = f"{str(request.base_url).rstrip('/')}/v1"
    tiles = f"{base}/collections/{col.id}/tiles/{TMS}"
    return {
        "title": col.title,
        "dataType": "vector",
        "tileMatrixSetURI": TMS_URI,
        "crs": "http://www.opengis.net/def/crs/EPSG/0/3857",
        "links": [
            {"rel": "self", "type": "application/json", "href": tiles},
            {
                "rel": "http://www.opengis.net/def/rel/ogc/1.0/tiling-scheme",
                "type": "application/json",
                "href": f"{base}/tileMatrixSets/{TMS}",
            },
            {
                "rel": "item",
                "type": "application/vnd.mapbox-vector-tile",
                "templated": True,
                "href": f"{tiles}/{{tileMatrix}}/{{tileRow}}/{{tileCol}}",
            },
        ],
    }


@router.get("/tileMatrixSets")
def list_tile_matrix_sets(request: Request):
    base = f"{str(request.base_url).rstrip('/')}/v1"
    return {
        "tileMatrixSets": [
            {
                "id": TMS,
                "title": "Google Maps Compatible for the World",
                "uri": TMS_URI,
                "links": [{"rel": "self", "href": f"{base}/tileMatrixSets/{TMS}"}],
            }
        ]
    }


@router.get("/tileMatrixSets/{tms_id}")
def get_tile_matrix_set(tms_id: str):
    if tms_id != TMS:
        raise HTTPException(status_code=404, detail="unknown tile matrix set")
    return wms.tile_matrix_set_json()


@router.get("/collections/{collection_id}/tiles")
def list_tilesets(
    collection_id: str,
    request: Request,
    user=Depends(get_current_user_optional),
    guest: GuestActor | None = Depends(get_share_link_actor),
    session: Session = Depends(get_session, scope="function"),
):
    col = _tiles_collection(session, user, guest, collection_id)
    return {"tilesets": [_tileset(request, col)]}


@router.get("/collections/{collection_id}/tiles/{tms}")
def get_tileset(
    collection_id: str,
    tms: str,
    request: Request,
    user=Depends(get_current_user_optional),
    guest: GuestActor | None = Depends(get_share_link_actor),
    session: Session = Depends(get_session, scope="function"),
):
    col = _tiles_collection(session, user, guest, collection_id)
    if tms != TMS:
        raise HTTPException(status_code=404, detail="unknown tile matrix set")
    return _tileset(request, col)


def _tiles_collection(session, user, guest, collection_id: str):
    try:
        return _readable(session, user, guest, collection_id, "collectionId")
    except _OwsError as e:
        raise HTTPException(status_code=e.status, detail=e.message) from e


@router.get("/collections/{collection_id}/tiles/{tms}/{tile_matrix}/{tile_row}/{tile_col}")
def get_ogc_tile(
    collection_id: str,
    tms: str,
    tile_matrix: int,
    tile_row: int,
    tile_col: int,
    request: Request,
    user=Depends(get_current_user_optional),
    guest: GuestActor | None = Depends(get_share_link_actor),
    session: Session = Depends(get_session, scope="function"),
    introspect=Depends(get_introspector),
    rls=Depends(get_rls_scope),
    masked=Depends(get_masked_for_user),
) -> Response:
    """Même rendu (mêmes octets, ETag, plafonds, RLS, masquage) que la route
    `/tiles/{z}/{x}/{y}.mvt` : délégation directe, aucune seconde requête SQL."""
    _tiles_collection(session, user, guest, collection_id)
    if tms != TMS:
        raise HTTPException(status_code=404, detail="unknown tile matrix set")
    return get_collection_tile(
        collection_id,
        tile_matrix,
        tile_col,  # x
        tile_row,  # y
        request,
        bin=None,  # le binning ARC-22 reste propre à la route `.mvt`
        stat="count",
        field=None,
        bins=16,
        user=user,
        guest=guest,
        session=session,
        introspect=introspect,
        rls=rls,
        masked=masked,
    )
